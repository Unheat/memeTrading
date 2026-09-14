"""Tests for app.agent.tools registry and duplicate call protection."""
from unittest.mock import patch, MagicMock
import pytest
from app.agent.tools import create_agent_tools, ToolCallGuard


def test_tool_registry_contains_all_10_tools():
    tools = create_agent_tools()
    tool_names = {t.name for t in tools}
    expected = {
        "search_social",
        "search_articles",
        "read_article",
        "search_web",
        "get_market_data",
        "get_company_research",
        "list_sec_filings",
        "pull_sec_filings",
        "verify_sec_claim",
        "get_sec_financials",
    }
    assert tool_names == expected


def test_duplicate_call_guard_suppresses_repeated_calls():
    guard = ToolCallGuard(max_identical=2)
    sig = ("search_web", (("query", "NVDA partnership"),))

    # First two calls allowed
    assert guard.check_and_record(sig) is False
    assert guard.check_and_record(sig) is False

    # Third identical call suppressed
    assert guard.check_and_record(sig) is True


def test_tool_execution_catches_errors_gracefully():
    tools = create_agent_tools()
    market_tool = next(t for t in tools if t.name == "get_market_data")

    # Invalid ticker should return structured error string, not crash loop
    res = market_tool.invoke({"ticker": ""})
    assert "error" in str(res).lower() or "invalid" in str(res).lower()


def test_verify_sec_claim_tool_wires_embedder_and_assessor(tmp_path):
    from app.sec.schemas import FilingMetadata, DownloadedDocument, PulledCorpus
    from app.storage.cases import write_corpus_manifest
    from datetime import datetime, timezone, date

    case_id = "MU-2026-09-01-001"
    case_dir = tmp_path / case_id
    doc_dir = case_dir / "sec" / "documents"
    doc_dir.mkdir(parents=True)

    from hashlib import sha256

    doc_path = doc_dir / "8k.htm"
    text_content = "Gross margin expanded to 36 percent. The agreement is non-binding."
    doc_path.write_text(text_content, encoding="utf-8")
    actual_hash = sha256(text_content.encode("utf-8")).hexdigest()

    corpus = PulledCorpus(
        corpus_id=case_id,
        ticker="MU",
        cik="723125",
        created_at=datetime.now(timezone.utc),
        documents=(
            DownloadedDocument(
                accession="0001193125-26-000001",
                form="8-K",
                filing_date=date(2026, 9, 1),
                document_name="8k.htm",
                source_url="https://www.sec.gov/8k.htm",
                relative_path="sec/documents/8k.htm",
                sha256=actual_hash,
            ),
        ),
    )
    write_corpus_manifest(case_dir, corpus)

    tools = create_agent_tools(cases_root=tmp_path)
    verify_tool = next(t for t in tools if t.name == "verify_sec_claim")

    # Invoking verify_sec_claim should automatically prepare, index, and verify!
    output_str = verify_tool.invoke({"corpus_id": case_id, "claim": "Gross margin expanded to 36 percent"})
    import json
    data = json.loads(output_str)
    assert data.get("status") == "ok"
    assert data.get("verification") is not None
    assert data["verification"]["verdict"] == "CONFIRMED"


def test_pull_sec_filings_tool_invocation(tmp_path, monkeypatch):
    """Verify pull_sec_filings correctly constructs SelectedSecDocument and FilingMetadata."""
    import json
    from datetime import date, datetime, timezone
    from app.sec.pull import FilingPullResult
    from app.sec.schemas import DownloadedDocument, PulledCorpus
    import app.agent.tools as tools_mod

    case_id = "MU-2026-09-01-001"

    def fake_pull(cases_root, case_id, selections):
        assert len(selections) == 1
        assert selections[0].filing.accession == "0001193125-26-000001"
        assert selections[0].filing.form == "8-K"
        assert selections[0].document_name == "primary_doc.htm"
        return FilingPullResult(
            corpus=PulledCorpus(
                corpus_id=case_id,
                ticker="MU",
                cik="723125",
                created_at=datetime.now(timezone.utc),
                documents=(
                    DownloadedDocument(
                        accession="0001193125-26-000001",
                        form="8-K",
                        filing_date=date(2026, 9, 1),
                        document_name="primary_doc.htm",
                        source_url="https://www.sec.gov/8k.htm",
                        relative_path="sec/documents/primary_doc.htm",
                        sha256="a" * 64,
                    ),
                ),
            ),
            error=None,
        )

    monkeypatch.setattr(tools_mod, "_pull_sec_filings", fake_pull)
    tools = create_agent_tools(cases_root=tmp_path)
    pull_tool = next(t for t in tools if t.name == "pull_sec_filings")

    res = pull_tool.invoke({
        "case_id": case_id,
        "selections": [
            {
                "accession": "0001193125-26-000001",
                "form": "8-K",
                "filing_date": "2026-09-01",
                "document_name": "primary_doc.htm",
                "source_url": "https://www.sec.gov/8k.htm",
                "ticker": "MU",
                "cik": "723125",
            }
        ],
    })
    data = json.loads(res)
    assert data["status"] == "ok"
    assert data["corpus"]["corpus_id"] == case_id
