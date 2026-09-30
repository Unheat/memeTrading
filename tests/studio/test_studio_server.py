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
    assert "step-pill-scout" in html
    assert "step-pill-plan" in html
    assert "trace-events-stream" in html
    assert "trace-pulse-dot" in html
    assert "llm_thinking" in html


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


