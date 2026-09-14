"""Unified runner executing the outer market research agent.

Donor provenance: adapted from reference/ai-financial-research-agent/app/api/service.py:40-110.
Runs the compiled LangGraph loop, manages case directory storage, and saves
the finished forensic memo and structured investigation JSON.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.agent.graph import create_agent_graph
from app.agent.media import generate_media_package
from app.agent.model_runtime import ModelRuntime, create_default_model_runtime
from app.agent.memo import render_forensic_memo, serialize_investigation_json
from app.agent.state import InvestigationState, ResearchRequest, create_initial_state
from app.agent.tools import ToolCallGuard, create_agent_tools
from app.config import AppConfig, load_config
from app.storage.cases import case_path, create_case_id

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


def _resolve_case_id(root: Path, ticker: str) -> str:
    """Generate a unique sequential case identifier for today."""
    today = date.today()
    clean_ticker = ticker if ticker.isalpha() and 1 <= len(ticker) <= 10 else "RESEARCH"
    for seq in range(1, 1000):
        cid = create_case_id(clean_ticker, today, seq)
        target = case_path(root, cid)
        if not target.exists():
            return cid
    return create_case_id(clean_ticker, today, 999)


def run_investigation(
    request: ResearchRequest,
    model: Any | None = None,
    cases_root: Path | str | None = None,
    generate_media: bool | None = None,
    character_pair: str | None = None,
    config: AppConfig | None = None,
) -> InvestigationResult:
    """Run an autonomous forensic market investigation.

    :param request: Validated ResearchRequest.
    :param model: Optional LLM model or test double.
    :param cases_root: Base storage directory (defaults to config or 'cases').
    :param generate_media: Whether to generate article.md and faceless reel dialogue.
    :param character_pair: Duo for reel script: 'peter_stewie' or 'rick_morty'.
    :param config: Optional AppConfig instance (loads from config.yaml if omitted).
    :returns: InvestigationResult containing case ID, status, rendered memo, and article.
    """
    cfg = config or load_config()
    effective_cases_root = cases_root or cfg.research.cases_root
    effective_generate_media = generate_media if generate_media is not None else cfg.media.generate_media
    effective_character_pair = character_pair or cfg.media.character_pair

    root = Path(effective_cases_root)
    root.mkdir(parents=True, exist_ok=True)

    ticker = request.ticker or "RESEARCH"
    case_id = _resolve_case_id(root, ticker)
    target_case_dir = case_path(root, case_id)
    target_case_dir.mkdir(parents=True, exist_ok=True)

    initial_state = create_initial_state(request, case_id=case_id)
    guard = ToolCallGuard(max_identical=request.budget.max_identical_calls)
    tools = create_agent_tools(cases_root=root, guard=guard)

    if model is not None:
        runtime = ModelRuntime(model=model)
    else:
        runtime = create_default_model_runtime(
            model=cfg.llm.model,
            base_url=cfg.llm.base_url,
            temperature=cfg.llm.temperature,
        )
    model = runtime.model
    graph = create_agent_graph(
        model=model,
        tools=tools,
        context_policy=runtime.context_policy,
        token_counter=runtime.token_counter,
    )

    logger.info("Starting investigation %s for $%s", case_id, ticker)
    final_state = dict(graph.invoke(initial_state))
    final_state["status"] = "completed"

    messages = final_state.get("messages", [])
    last_message = messages[-1] if messages else None
    final_text = getattr(last_message, "content", "") if last_message else ""

    memo_md = render_forensic_memo(final_state, final_text)
    investigation_json = serialize_investigation_json(final_state, memo_md)

    # Save case artifacts
    memo_file = target_case_dir / "memo.md"
    json_file = target_case_dir / "investigation.json"

    memo_file.write_text(memo_md, encoding="utf-8")
    json_file.write_text(json.dumps(investigation_json, indent=2), encoding="utf-8")

    article_md: str | None = None
    if effective_generate_media:
        try:
            pkg = generate_media_package(final_state, model=model, character_pair=effective_character_pair)
            article_md = pkg.article_markdown

            # Write article.md
            (target_case_dir / "article.md").write_text(pkg.article_markdown, encoding="utf-8")

            # Write Faceless input files under cases/<case_id>/faceless/
            faceless_dir = target_case_dir / "faceless"
            faceless_dir.mkdir(parents=True, exist_ok=True)
            (faceless_dir / "dialogue.json").write_text(json.dumps(pkg.dialogue_json, indent=2), encoding="utf-8")
            (faceless_dir / "source-script.txt").write_text(pkg.reel_script_text, encoding="utf-8")
            (faceless_dir / "reel_script.txt").write_text(pkg.reel_script_text, encoding="utf-8")
            (faceless_dir / "caption.txt").write_text(pkg.caption_text, encoding="utf-8")
        except Exception as exc:
            logger.warning("Media generation failed for %s: %s", case_id, exc)

    logger.info("Investigation %s finished. Artifacts written to %s", case_id, target_case_dir)

    return InvestigationResult(
        case_id=case_id,
        ticker=ticker,
        status=final_state.get("status", "completed"),
        memo_markdown=memo_md,
        final_state=dict(final_state),
        article_markdown=article_md,
    )
