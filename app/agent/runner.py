"""Unified runner executing the outer market research agent.

Adapted manifest lifecycle semantics from
reference/ai-financial-research-agent/app/api/schemas.py:13-19,64-84 and
reference/ai-financial-research-agent/app/api/service.py:81-94,163-198.
No FastAPI, database, threads, or event fanout are used.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agent.graph import create_research_graph
from app.agent.media import generate_article_markdown, generate_reel_script
from app.agent.model_runtime import ModelRuntime, create_default_model_runtime
from app.agent.memo import render_forensic_memo, render_research_report, serialize_investigation_json
from app.agent.state import BudgetLimits, ResearchRequest, create_initial_state
from app.agent.tools import ToolCallGuard, create_agent_tools
from app.config import AppConfig, load_config
from app.media.faceless_bridge import FacelessBridge
from app.storage.cases import allocate_case, write_run_manifest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvestigationResult:
    """Outcome of an end-to-end forensic research run."""

    case_id: str
    ticker: str
    status: str
    memo_markdown: str
    final_state: dict[str, Any]
    article_markdown: str | None = None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Persist a JSON artifact with deterministic formatting.

    Args:
        path: Destination case-local artifact path.
        payload: JSON-safe artifact object.

    Returns:
        None.
    """
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def run_investigation(
    request: ResearchRequest,
    model: Any | None = None,
    cases_root: Path | str | None = None,
    generate_article: bool | None = None,
    generate_video: bool | None = None,
    render_video: bool | None = None,
    character_pair: str | None = None,
    config: AppConfig | None = None,
    # Legacy parameter preserved for backward compatibility
    generate_media: bool | None = None,
) -> InvestigationResult:
    """Run an autonomous forensic market investigation.

    Args:
        request: Validated research direction.
        model: Optional model or deterministic test double.
        cases_root: Case storage root, defaulting to configured location.
        generate_article: Whether to generate the cited Substack article.
        generate_video: Whether to generate dialogue script (and optionally render video).
        render_video: Whether to invoke the Faceless Node.js pipeline for .mp4 rendering.
        character_pair: Optional media character pair.
        config: Optional preloaded configuration.
        generate_media: Legacy flag. True enables article + video script.

    Returns:
        Investigation outcome and persisted case artifacts.

    Raises:
        Exception: Re-raises graph or core artifact failure after failed manifest write.
    """
    cfg = config or load_config()
    root = Path(cases_root or cfg.research.cases_root)
    ticker = request.ticker or "RESEARCH"
    case_id, target_case_dir = allocate_case(root, ticker)
    started_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "case_id": case_id,
        "status": "running",
        "created_at": started_at,
        "started_at": started_at,
        "request": {"query": request.query, "ticker": request.ticker, "company": request.company, "theme": request.theme, "depth": request.depth},
        "artifacts": [],
        "last_stage": "allocated",
    }
    write_run_manifest(target_case_dir, manifest)

    try:
        # Resolve media flags: explicit param > legacy generate_media > config defaults
        if generate_media is not None:
            effective_article = generate_article if generate_article is not None else generate_media
            effective_video = generate_video if generate_video is not None else generate_media
        else:
            effective_article = generate_article if generate_article is not None else cfg.media.generate_article
            effective_video = generate_video if generate_video is not None else cfg.media.generate_video
        effective_render = render_video if render_video is not None else cfg.media.render_video
        effective_pair = character_pair or cfg.media.character_pair

        configured_budget = BudgetLimits(cfg.research.max_tool_calls, cfg.research.max_identical_calls)
        budget = configured_budget if request.budget == BudgetLimits() else request.budget
        effective_request = ResearchRequest(
            query=request.query, ticker=request.ticker, company=request.company, theme=request.theme,
            mandate=request.mandate, time_boundary=request.time_boundary, budget=budget,
            template_version=request.template_version, depth=request.depth,
            requested_ranking_count=request.requested_ranking_count,
            requested_position_decision=request.requested_position_decision,
        )
        initial_state = create_initial_state(effective_request, case_id=case_id)
        manifest["research_intent"] = initial_state["research_intent"]
        runtime = ModelRuntime(model=model) if model is not None else create_default_model_runtime(
            model=cfg.llm.model, base_url=cfg.llm.base_url, temperature=cfg.llm.temperature, endpoints=cfg.llm.models,
        )
        tools = create_agent_tools(
            cases_root=root,
            guard=ToolCallGuard(max_identical=budget.max_identical_calls),
            model=runtime.model,
            case_id=case_id,
        )
        graph = create_research_graph(
            runtime.model, tools, context_policy=runtime.context_policy, token_counter=runtime.token_counter,
        )
        logger.info(
            "pipeline.start case_id=%s ticker=%s depth=%s budget=%s intent=%s",
            case_id, ticker, effective_request.depth, budget.max_total_tool_calls, initial_state["research_intent"],
        )
        final_state = dict(graph.invoke(initial_state, config={"recursion_limit": 100}))
        logger.info(
            "pipeline.graph_complete case_id=%s status=%s tool_calls=%s candidates=%s receipts=%s evidence=%s",
            case_id, final_state.get("status"), final_state.get("tool_calls"), len(final_state.get("candidates") or {}),
            len(final_state.get("searches_performed") or []), len(final_state.get("evidence") or []),
        )

        messages = final_state.get("messages", [])
        last_message = messages[-1] if messages else None
        final_text = getattr(last_message, "content", "") if last_message else ""
        explicit_position_request = bool((final_state.get("research_intent") or {}).get("requested_position_decision"))
        memo_md = (
            render_forensic_memo(final_state, final_text)
            if explicit_position_request and final_state.get("ticker")
            else render_research_report(final_state, final_text)
        )
        _write_json(target_case_dir / "investigation.json", serialize_investigation_json(final_state, memo_md))
        (target_case_dir / "memo.md").write_text(memo_md, encoding="utf-8")
        logger.info("pipeline.artifacts_written case_id=%s memo_kind=%s", case_id, "forensic" if explicit_position_request else "research")

        # --- Post-Graph Media Stages (opt-in) ---
        article_md: str | None = None
        artifacts_list = ["memo.md", "investigation.json"]

        # Stage A: Article generation
        if effective_article:
            try:
                article_md = generate_article_markdown(memo_md, final_state, model=runtime.model)
                (target_case_dir / "article.md").write_text(article_md, encoding="utf-8")
                artifacts_list.append("article.md")
                logger.info("pipeline.article_written case_id=%s", case_id)
            except Exception as exc:
                logger.warning("Article generation failed for %s: %s", case_id, exc)

        # Stage B: Video script generation
        if effective_video:
            try:
                source_text = article_md or memo_md
                dialogue_json, reel_script_text, caption_text = generate_reel_script(
                    source_text,
                    model=runtime.model,
                    character_pair=effective_pair,
                    reel_temperature=cfg.media.reel_temperature,
                )
                faceless_dir = target_case_dir / "faceless"
                faceless_dir.mkdir(parents=True, exist_ok=True)
                dialogue_path = faceless_dir / "dialogue.json"
                dialogue_path.write_text(json.dumps(dialogue_json, indent=2), encoding="utf-8")
                (faceless_dir / "source-script.txt").write_text(reel_script_text, encoding="utf-8")
                (faceless_dir / "reel_script.txt").write_text(reel_script_text, encoding="utf-8")
                (faceless_dir / "caption.txt").write_text(caption_text, encoding="utf-8")
                artifacts_list.append("faceless/dialogue.json")
                logger.info("pipeline.reel_script_written case_id=%s", case_id)

                # Stage C: Video rendering via Faceless bridge (subprocess to external Node.js)
                if effective_render:
                    topic_slug = ticker.lower().replace(" ", "-")
                    bridge = FacelessBridge()
                    final_video = bridge.compose_reel(
                        dialogue_path=dialogue_path,
                        topic_slug=topic_slug,
                        output_dir=faceless_dir,
                        fish_model=cfg.media.fish_model,
                    )
                    if final_video:
                        artifacts_list.append("faceless/final-faceless-reel.mp4")
                        logger.info("pipeline.video_rendered case_id=%s path=%s", case_id, final_video)
                    else:
                        logger.warning("Video rendering skipped or failed for %s", case_id)
            except Exception as exc:
                logger.warning("Video script generation failed for %s: %s", case_id, exc)

        candidates_map = final_state.get("candidates") or {}
        total_sources = len(final_state.get("source_records", []))
        total_evidence = len(final_state.get("evidence", []))
        for cand in candidates_map.values():
            if isinstance(cand, Mapping):
                total_evidence += len(cand.get("evidence", []))
                if cand.get("market_context"):
                    total_evidence += 1
                if cand.get("sec_financials"):
                    total_evidence += 1

        manifest.update({
            "status": "completed", "finished_at": datetime.now(timezone.utc).isoformat(),
            "last_stage": "rendered", "research_status": final_state["status"],
            "artifacts": artifacts_list,
            "receipt_summary": final_state.get("searches_performed", []),
            "source_count": total_sources,
            "evidence_count": total_evidence,
            "provider_failures": [receipt for receipt in final_state.get("searches_performed", []) if receipt.get("status") == "error"],
        })
        write_run_manifest(target_case_dir, manifest)
        return InvestigationResult(case_id, ticker, final_state["status"], memo_md, final_state, article_md)
    except Exception as exc:
        manifest.update({
            "status": "failed", "finished_at": datetime.now(timezone.utc).isoformat(),
            "last_stage": manifest.get("last_stage", "allocated"),
            "error": {"type": type(exc).__name__, "message": str(exc)[:500]},
        })
        write_run_manifest(target_case_dir, manifest)
        raise
