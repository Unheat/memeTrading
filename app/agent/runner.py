"""Unified runner executing the outer market research agent.

Adapted manifest lifecycle semantics from
reference/ai-financial-research-agent/app/api/schemas.py:13-19,64-84 and
reference/ai-financial-research-agent/app/api/service.py:81-94,163-198.
No FastAPI, database, threads, or event fanout are used.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agent.graph import create_research_graph
from app.agent.media import generate_media_package
from app.agent.model_runtime import ModelRuntime, create_default_model_runtime
from app.agent.memo import render_forensic_memo, render_research_report, serialize_investigation_json
from app.agent.state import BudgetLimits, ResearchRequest, create_initial_state
from app.agent.tools import ToolCallGuard, create_agent_tools
from app.config import AppConfig, load_config
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
    generate_media: bool | None = None,
    character_pair: str | None = None,
    config: AppConfig | None = None,
) -> InvestigationResult:
    """Run an autonomous forensic market investigation.

    Args:
        request: Validated research direction.
        model: Optional model or deterministic test double.
        cases_root: Case storage root, defaulting to configured location.
        generate_media: Whether optional media artifacts are requested.
        character_pair: Optional media character pair.
        config: Optional preloaded configuration.

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
        effective_media = generate_media if generate_media is not None else cfg.media.generate_media
        effective_pair = character_pair or cfg.media.character_pair
        configured_budget = BudgetLimits(cfg.research.max_tool_calls, cfg.research.max_identical_calls)
        budget = configured_budget if request.budget == BudgetLimits() else request.budget
        effective_request = ResearchRequest(
            query=request.query, ticker=request.ticker, company=request.company, theme=request.theme,
            mandate=request.mandate, time_boundary=request.time_boundary, budget=budget,
            template_version=request.template_version, depth=request.depth,
        )
        initial_state = create_initial_state(effective_request, case_id=case_id)
        manifest["research_intent"] = initial_state["research_intent"]
        tools = create_agent_tools(cases_root=root, guard=ToolCallGuard(max_identical=budget.max_identical_calls))
        runtime = ModelRuntime(model=model) if model is not None else create_default_model_runtime(
            model=cfg.llm.model, base_url=cfg.llm.base_url, temperature=cfg.llm.temperature, endpoints=cfg.llm.models,
        )
        graph = create_research_graph(
            runtime.model, tools, context_policy=runtime.context_policy, token_counter=runtime.token_counter,
        )
        logger.info("Starting deep research investigation %s for %s", case_id, ticker)
        final_state = dict(graph.invoke(initial_state))

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

        article_md: str | None = None
        if (
            bool((final_state.get("research_intent") or {}).get("requested_position_decision"))
            and effective_media
            and final_state["status"] not in ("insufficient_evidence", "research_incomplete", "validation_required")
        ):
            try:
                package = generate_media_package(
                    final_state,
                    model=runtime.model,
                    character_pair=effective_pair,
                    reel_temperature=cfg.media.reel_temperature,
                )
                article_md = package.article_markdown
                (target_case_dir / "article.md").write_text(article_md, encoding="utf-8")
                faceless_dir = target_case_dir / "faceless"
                faceless_dir.mkdir(parents=True, exist_ok=True)
                (faceless_dir / "dialogue.json").write_text(json.dumps(package.dialogue_json, indent=2), encoding="utf-8")
                (faceless_dir / "source-script.txt").write_text(package.reel_script_text, encoding="utf-8")
                (faceless_dir / "reel_script.txt").write_text(package.reel_script_text, encoding="utf-8")
                (faceless_dir / "caption.txt").write_text(package.caption_text, encoding="utf-8")
            except Exception as exc:
                logger.warning("Media generation failed for %s: %s", case_id, exc)

        manifest.update({
            "status": "completed", "finished_at": datetime.now(timezone.utc).isoformat(),
            "last_stage": "rendered", "research_status": final_state["status"],
            "artifacts": ["memo.md", "investigation.json"] + (["article.md"] if article_md else []),
            "receipt_summary": final_state.get("searches_performed", []),
            "source_count": len(final_state.get("source_records", [])),
            "evidence_count": len(final_state.get("evidence", [])),
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
