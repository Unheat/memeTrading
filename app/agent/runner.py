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
from app.agent.memo import render_forensic_memo, serialize_investigation_json
from app.agent.state import InvestigationState, ResearchRequest, create_initial_state
from app.agent.tools import create_agent_tools
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
) -> InvestigationResult:
    """Run an autonomous forensic market investigation.

    :param request: Validated ResearchRequest.
    :param model: Optional LLM model or test double.
    :param cases_root: Base storage directory (defaults to 'cases').
    :returns: InvestigationResult containing case ID, status, and rendered memo.
    """
    root = Path(cases_root) if cases_root else Path("cases")
    root.mkdir(parents=True, exist_ok=True)

    ticker = request.ticker or "RESEARCH"
    case_id = _resolve_case_id(root, ticker)
    target_case_dir = case_path(root, case_id)
    target_case_dir.mkdir(parents=True, exist_ok=True)

    initial_state = create_initial_state(request, case_id=case_id)
    tools = create_agent_tools(cases_root=root)

    if model is None:
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(model="gpt-4o", temperature=0)

    graph = create_agent_graph(model=model, tools=tools)

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

    logger.info("Investigation %s finished. Artifacts written to %s", case_id, target_case_dir)

    return InvestigationResult(
        case_id=case_id,
        ticker=ticker,
        status=final_state.get("status", "completed"),
        memo_markdown=memo_md,
        final_state=dict(final_state),
    )
