"""Unit tests for the Local Studio server and endpoints."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.studio.server import get_all_cases, get_studio_html


def test_get_all_cases(tmp_path: Path) -> None:
    """Verify scanning case folders extracts ticker, flags, and titles."""
    cases_root = tmp_path / "cases"
    cases_root.mkdir()

    case_1 = cases_root / "NVDA-2026-09-18-001"
    case_1.mkdir()
    (case_1 / "article.md").write_text("# NVDA Cloud Bottleneck Audit\nContent...", encoding="utf-8")
    (case_1 / "investigation.json").write_text(json.dumps({"ticker": "NVDA"}), encoding="utf-8")

    cases = get_all_cases(cases_root=str(cases_root))
    assert len(cases) == 1
    assert cases[0]["ticker"] == "NVDA"
    assert cases[0]["title"] == "NVDA Cloud Bottleneck Audit"
    assert cases[0]["has_article"] is True
    assert cases[0]["has_video"] is False
    assert cases[0]["publication_status"] == "blocked"
    assert cases[0]["is_publishable"] is False

    # Publishable case
    case_2 = cases_root / "MU-2026-09-18-002"
    case_2.mkdir()
    (case_2 / "investigation.json").write_text(
        json.dumps({"ticker": "MU", "publication_readiness": {"status": "publishable", "passed": True}}),
        encoding="utf-8",
    )
    cases_updated = get_all_cases(cases_root=str(cases_root))
    assert len(cases_updated) == 2
    mu_case = next(c for c in cases_updated if c["ticker"] == "MU")
    assert mu_case["publication_status"] == "publishable"
    assert mu_case["is_publishable"] is True


def test_get_studio_html() -> None:
    """Verify HTML interface includes critical controls and script tags."""
    html = get_studio_html()
    assert "MEMETRADING LOCAL STUDIO" in html
    assert "btn-run-article" in html
    assert "btn-run-all" in html
    assert "btn-publish-submit" in html
    assert "tab-trace" in html
    assert "Live Model Trace" in html
    assert "trace-rail-progress" in html
    assert "trace-events-stream" in html
    assert "trace-pulse-dot" in html
    assert "llm_thinking" in html
    assert "AGENT_PROFILE" in html
    assert "toggleThink" in html


def test_get_active_job_snapshot() -> None:
    """Verify thread-safe snapshot returns consistent dictionary."""
    from app.studio.server import _ACTIVE_JOB, _JOB_LOCK, get_active_job_snapshot

    with _JOB_LOCK:
        _ACTIVE_JOB["status"] = "running"
        _ACTIVE_JOB["case_id"] = "TEST-001"
        _ACTIVE_JOB["job_id"] = "job-12345"
        _ACTIVE_JOB["events"] = [{"seq": 1, "title": "Test"}]
        _ACTIVE_JOB["log"] = ["Log message 1"]

    snap = get_active_job_snapshot()
    assert snap["status"] == "running"
    assert snap["case_id"] == "TEST-001"
    assert snap["job_id"] == "job-12345"
    assert snap["events_count"] == 1
    assert snap["log"] == ["Log message 1"]

    # Reset
    with _JOB_LOCK:
        _ACTIVE_JOB["status"] = "idle"
        _ACTIVE_JOB["case_id"] = None
        _ACTIVE_JOB["job_id"] = None
        _ACTIVE_JOB["events"] = []
        _ACTIVE_JOB["log"] = []


def test_investigation_callback_handler() -> None:
    """Verify InvestigationCallbackHandler records and serializes events correctly."""
    from uuid import uuid4
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from app.agent.callbacks import InvestigationCallbackHandler

    emitted = []
    handler = InvestigationCallbackHandler(event_callback=lambda ev: emitted.append(ev), case_id="TEST-CASE")

    # 1. Stage transition
    handler.emit_stage("planner", "Planning investigation", {"query": "test query"})
    assert len(handler.events) == 1
    assert handler.events[0]["seq"] == 1
    assert handler.events[0]["event_type"] == "stage"
    assert handler.events[0]["stage"] == "planner"
    assert handler.events[0]["case_id"] == "TEST-CASE"

    # 2. Tool invocation
    handler.on_tool_start(
        serialized={"name": "get_market_data"},
        input_str='{"ticker": "NVDA"}',
        run_id=uuid4(),
    )
    assert len(handler.events) == 2
    assert handler.events[1]["seq"] == 2
    assert handler.events[1]["event_type"] == "tool_call"
    assert handler.events[1]["payload"]["tool"] == "get_market_data"
    assert handler.events[1]["payload"]["ticker"] == "NVDA"

    # 3. Tool completion
    handler.on_tool_end("Market data for NVDA: $120.50", run_id=uuid4())
    assert len(handler.events) == 3
    assert handler.events[2]["seq"] == 3
    assert handler.events[2]["event_type"] == "tool_result"
    assert handler.events[2]["payload"]["status"] == "ok"

    # 4. LLM response with model thinking
    ai_msg = AIMessage(
        content="I will evaluate NVDA valuation now.",
        additional_kwargs={"reasoning_content": "We need to check the inventory trajectory first..."},
    )
    result = ChatResult(generations=[ChatGeneration(message=ai_msg)])
    handler.on_llm_end(result, run_id=uuid4())

    # Generates thinking event + response event
    assert len(handler.events) == 5
    thinking_ev = handler.events[3]
    assert thinking_ev["event_type"] == "llm_thinking"
    assert "inventory trajectory" in thinking_ev["payload"]["thinking"]

    resp_ev = handler.events[4]
    assert resp_ev["event_type"] == "llm_response"
    assert "evaluate NVDA" in resp_ev["payload"]["content_preview"]

    # Verify callback listener received all events
    assert len(emitted) == 5


def test_job_events_server_endpoint() -> None:
    """Verify HTTP GET /api/job-events returns events with since filtering."""
    import urllib.request
    from http.server import ThreadingHTTPServer
    import threading
    from app.studio.server import StudioHandler, _ACTIVE_JOB, _JOB_LOCK

    with _JOB_LOCK:
        _ACTIVE_JOB["status"] = "running"
        _ACTIVE_JOB["case_id"] = "CASE-LIVE"
        _ACTIVE_JOB["job_id"] = "job-999"
        _ACTIVE_JOB["events"] = [
            {"seq": 1, "title": "Step 1", "event_type": "stage"},
            {"seq": 2, "title": "Step 2", "event_type": "tool_call"},
            {"seq": 3, "title": "Step 3", "event_type": "tool_result"},
        ]

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), StudioHandler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        # 1. Fetch all events (since=0)
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/job-events?since=0")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "running"
            assert data["job_id"] == "job-999"
            assert len(data["events"]) == 3
            assert data["next_seq"] == 3

        # 2. Fetch incremental events (since=2)
        req2 = urllib.request.Request(f"http://127.0.0.1:{port}/api/job-events?since=2")
        with urllib.request.urlopen(req2) as resp:
            data2 = json.loads(resp.read().decode("utf-8"))
            assert len(data2["events"]) == 1
            assert data2["events"][0]["title"] == "Step 3"
    finally:
        httpd.shutdown()
        httpd.server_close()
        with _JOB_LOCK:
            _ACTIVE_JOB["status"] = "idle"
            _ACTIVE_JOB["case_id"] = None
            _ACTIVE_JOB["job_id"] = None
            _ACTIVE_JOB["events"] = []
            _ACTIVE_JOB["log"] = []




def test_normalize_legacy_stage_events() -> None:
    """Verify pre-stage-tracking runs are re-labeled deterministically on replay."""
    from app.agent.callbacks import normalize_legacy_stage_events

    legacy_events = [
        {"seq": 1, "event_type": "stage", "stage": "planner", "title": "Launching investigation", "payload": {}},
        {"seq": 2, "event_type": "llm_start", "stage": "planner", "title": "Chat Model Turn", "payload": {}},
        {"seq": 3, "event_type": "tool_call", "stage": "planner", "title": "Calling screen_stocks",
         "payload": {"tool": "screen_stocks"}},
        {"seq": 4, "event_type": "tool_call", "stage": "planner", "title": "Calling search_web",
         "payload": {"tool": "search_web"}},
        {"seq": 5, "event_type": "llm_start", "stage": "planner", "title": "Chat Model Turn", "payload": {}},
        {"seq": 6, "event_type": "tool_call", "stage": "planner", "title": "Calling get_market_data",
         "payload": {"tool": "get_market_data", "ticker": "SMCI"}},
        {"seq": 7, "event_type": "tool_call", "stage": "planner", "title": "Calling investigate_sec",
         "payload": {"tool": "investigate_sec", "ticker": "SMCI"}},
        {"seq": 8, "event_type": "stage", "stage": "synthesis", "title": "Synthesizing memo", "payload": {}},
        {"seq": 9, "event_type": "stage", "stage": "article", "title": "Rendering article", "payload": {}},
    ]

    normalized = normalize_legacy_stage_events(legacy_events)

    # Scout-phase events stay planner
    assert normalized[0]["stage"] == "planner"
    assert normalized[2]["stage"] == "planner"
    assert normalized[3]["stage"] == "planner"

    # First non-scout tool call (seq 6) starts the executor phase
    assert normalized[5]["stage"] == "executor"
    assert normalized[6]["stage"] == "executor"

    # Legacy synthesis maps to diligence; article stays post-pipeline
    assert normalized[7]["stage"] == "diligence"
    assert normalized[8]["stage"] == "article"

    # Input list must not be mutated
    assert legacy_events[6]["stage"] == "planner"


def test_normalize_legacy_stage_events_passes_through_canonical() -> None:
    """Canonical runs must pass through the normalizer untouched."""
    from app.agent.callbacks import normalize_legacy_stage_events

    canonical = [
        {"seq": 1, "event_type": "stage", "stage": "planner", "title": "Scout", "payload": {}},
        {"seq": 2, "event_type": "stage", "stage": "executor", "title": "Loop", "payload": {}},
        {"seq": 3, "event_type": "stage", "stage": "ingest", "title": "Ingestion", "payload": {}},
        {"seq": 4, "event_type": "stage", "stage": "reflect", "title": "Reflection", "payload": {}},
        {"seq": 5, "event_type": "stage", "stage": "diligence", "title": "Verdict", "payload": {}},
    ]
    assert normalize_legacy_stage_events(canonical) == canonical


def test_generate_article_for_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify generate_article_for_case compiles article.md and updates manifest."""
    from app.media.cli import generate_article_for_case

    case_dir = tmp_path / "TEST-CASE-001"
    case_dir.mkdir()
    (case_dir / "memo.md").write_text("# Test Memo\nInstitutional content.", encoding="utf-8")
    (case_dir / "investigation.json").write_text(
        json.dumps({"ticker": "TEST", "publication_readiness": {"status": "publishable", "passed": True}}),
        encoding="utf-8",
    )
    (case_dir / "run-manifest.json").write_text(json.dumps({"status": "completed", "artifacts": ["memo.md", "investigation.json"]}), encoding="utf-8")

    monkeypatch.setattr(
        "app.media.cli.generate_article_markdown",
        lambda memo, inv, model: "# Compiled Article [1]\nGenerated successfully.",
    )

    art_path = generate_article_for_case(case_dir)
    assert art_path.exists()
    assert "Compiled Article" in art_path.read_text(encoding="utf-8")
    assert (case_dir / "article.md") == art_path

    manifest = json.loads((case_dir / "run-manifest.json").read_text(encoding="utf-8"))
    assert "article.md" in manifest["artifacts"]

    from app.agent.callbacks import normalize_legacy_stage_events

    canonical_events = [
        {"seq": 1, "event_type": "stage", "stage": "planner", "title": "Stage 1", "payload": {}},
        {"seq": 2, "event_type": "tool_call", "stage": "executor", "title": "Calling investigate_sec",
         "payload": {"tool": "investigate_sec", "ticker": "SMCI"}},
        {"seq": 3, "event_type": "stage", "stage": "ingest", "title": "Stage 3", "payload": {}},
    ]

    normalized = normalize_legacy_stage_events(canonical_events)
    assert normalized == canonical_events
