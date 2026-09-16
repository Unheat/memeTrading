"""Unit tests for deep research tools: document_reader, sec_evidence, insiders, and ledger."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.agent.ledger import (
    ResearchWorkItem,
    append_ledger_event,
    read_ledger_events,
    canonical_input_digest,
)
from app.articles.document_reader import read_document, _extract_document_links
from app.sec.insiders import get_ownership_and_insider_activity
from app.sec.evidence import search_sec_evidence, read_sec_evidence
from app.agent.screening import build_candidate_comparisons


def test_research_work_item_and_ledger_events(tmp_path: Path) -> None:
    """Verify work items validate and ledger events persist append-only."""
    item = ResearchWorkItem(
        work_id="work-1",
        question="What is Micron's HBM3E pricing power?",
        evidence_tier="primary_sec",
        priority=10,
        depth=1,
        candidate_id="cand_mu",
    )
    assert item.work_id == "work-1"
    assert item.status == "queued"

    case_dir = tmp_path / "TEST-2026-09-16-001"
    case_dir.mkdir()

    event1 = append_ledger_event(case_dir, "plan_created", {"work_items": [item.to_dict()]})
    event2 = append_ledger_event(case_dir, "tool_admitted", {"work_id": "work-1", "tool": "search_sec_evidence"})

    assert event1["event_type"] == "plan_created"
    assert event2["event_type"] == "tool_admitted"

    events = read_ledger_events(case_dir)
    assert len(events) == 2
    assert events[0]["payload"]["work_items"][0]["work_id"] == "work-1"
    assert events[1]["payload"]["tool"] == "search_sec_evidence"


def test_canonical_input_digest_deterministic() -> None:
    """Ensure idempotency digest produces identical hash regardless of dict key ordering."""
    d1 = canonical_input_digest("search_web", {"query": "NVDA", "limit": 10})
    d2 = canonical_input_digest("search_web", {"limit": 10, "query": "NVDA"})
    assert d1 == d2
    assert len(d1) == 64


def test_extract_document_links_harvests_pdfs_and_reports() -> None:
    """Harvest anchor tags pointing to PDFs and financial reports from HTML."""
    html_sample = b"""
    <html>
      <body>
        <nav><a href="/home">Home</a></nav>
        <main>
          <h1>Investor Relations</h1>
          <a href="/files/q2_earnings_presentation.pdf">Q2 2026 Presentation (PDF)</a>
          <a href="https://example.com/reports/annual_report_2025.pdf">2025 Annual Report</a>
          <a href="/financials/shareholder_letter">Shareholder Letter</a>
          <a href="javascript:void(0)">Click me</a>
        </main>
      </body>
    </html>
    """
    links = _extract_document_links(html_sample, "https://example.com/investors/")
    assert len(links) >= 3
    urls = [link["url"] for link in links]
    assert "https://example.com/files/q2_earnings_presentation.pdf" in urls
    assert "https://example.com/reports/annual_report_2025.pdf" in urls
    assert "https://example.com/financials/shareholder_letter" in urls
    assert any(link["is_pdf"] for link in links)


def test_read_document_handles_html_with_link_harvesting(monkeypatch) -> None:
    """Verify read_document returns clean text and discovered PDF links on HTML pages."""
    import app.articles.document_reader as doc_module

    html_bytes = b"<html><body><h1>Q3 Earnings</h1><p>Revenue grew 35%.</p><a href='/deck.pdf'>Presentation PDF</a></body></html>"
    monkeypatch.setattr(doc_module, "_fetch_bytes", lambda url, **_: (html_bytes, "text/html"))

    res = read_document("https://example.com/investor")
    assert res["status"] == "ok"
    assert res["content_type"] == "text/html"
    assert "Revenue grew 35%" in res["text"]
    assert len(res["discovered_documents"]) == 1
    assert res["discovered_documents"][0]["url"] == "https://example.com/deck.pdf"


def test_get_ownership_and_insider_activity_distinguishes_buys_and_sales(monkeypatch) -> None:
    """Verify insider activity correctly aggregates buys, sales, and net changes."""
    import app.sec.insiders as insiders_module

    fake_rows = [
        {"name": "Director A", "transaction_code": "P", "shares": 1000.0, "change": 1000.0, "price": 50.0},
        {"name": "Officer B", "transaction_code": "S", "shares": 500.0, "change": -500.0, "price": 52.0},
    ]
    mock_client = MagicMock()
    mock_client.is_configured = True
    mock_client.get_insider_transactions.return_value = fake_rows

    monkeypatch.setattr(insiders_module, "FinnhubClient", lambda: mock_client)
    monkeypatch.setattr(insiders_module, "list_sec_filings", lambda *args, **kwargs: MagicMock(filings=[]))

    res = get_ownership_and_insider_activity("TEST", candidate_id="cand_test")
    assert res["status"] == "ok"
    assert res["ticker"] == "TEST"
    assert res["candidate_id"] == "cand_test"
    assert res["summary"]["buys_count"] == 1
    assert res["summary"]["sales_count"] == 1
    assert res["summary"]["net_shares_change"] == 500.0


def test_build_candidate_comparisons_generates_normalized_comparison_cards() -> None:
    """Verify build_candidate_comparisons computes side-by-side metric comparison cards."""
    candidates = {
        "cand_msft": {
            "ticker": "MSFT",
            "market_context": {"quote": {"price": 450.0}, "fundamentals": {"pe_ratio": 32.5}},
            "sec_financials": {"periods": ["2026-Q2"], "gross_margin_pct": {"2026-Q2": 0.69}, "revenue": {"2026-Q2": 65e9}},
        },
        "cand_googl": {
            "ticker": "GOOGL",
            "market_context": {"quote": {"price": 180.0}, "fundamentals": {"pe_ratio": 24.1}},
            "sec_financials": {"periods": ["2026-Q2"], "gross_margin_pct": {"2026-Q2": 0.57}, "revenue": {"2026-Q2": 88e9}},
        },
    }
    cards = build_candidate_comparisons(candidates, ["cand_msft", "cand_googl"], metrics=["price", "pe_ratio", "gross_margin"])
    assert len(cards) == 3
    price_card = next(c for c in cards if c["metric_key"] == "price")
    assert price_card["candidate_values"]["MSFT"]["value"] == 450.0
    assert price_card["candidate_values"]["GOOGL"]["value"] == 180.0
    assert price_card["comparability"] == "comparable"

    gm_card = next(c for c in cards if c["metric_key"] == "gross_margin")
    assert gm_card["candidate_values"]["MSFT"]["value"] == 0.69
    assert gm_card["candidate_values"]["GOOGL"]["value"] == 0.57
    assert gm_card["period_basis"] == "2026-Q2"
