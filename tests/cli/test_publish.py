"""Unit tests for the publishing CLI and sync engine."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.cli.publish import (
    find_case_dir,
    parse_citations_from_article,
    publish_case,
)


def test_find_case_dir_latest_and_by_id(tmp_path: Path) -> None:
    """Verify finding case by ID, prefix, and '--latest'."""
    cases_root = tmp_path / "cases"
    cases_root.mkdir()

    case_1 = cases_root / "MU-2026-09-10-001"
    case_1.mkdir()
    case_2 = cases_root / "NVDA-2026-09-15-002"
    case_2.mkdir()

    # Find direct match
    assert find_case_dir("MU-2026-09-10-001", cases_root=cases_root) == case_1
    # Find by ticker prefix
    assert find_case_dir("NVDA", cases_root=cases_root) == case_2
    # Find latest (case_2 was created after case_1)
    assert find_case_dir("--latest", cases_root=cases_root) == case_2


def test_parse_citations_from_article() -> None:
    """Verify bibliography parsing when structured JSON cards are not present."""
    raw_article = """# Test Title
Article content with [1] and [2].

## Primary Sources & Regulatory Receipts
- [1] Form 10-K FY2024: Accession 0000723125-24-000075 - https://www.sec.gov/edgar/data/723125/000072312524000075/mu.htm
- [2] FactSet Consensus: https://factset.com
"""
    citations = parse_citations_from_article(raw_article)
    assert len(citations) == 2
    assert citations[0]["index"] == 1
    assert citations[0]["accession"] == "0000723125-24-000075"
    assert citations[0]["sourceType"] == "SEC Filing"
    assert citations[1]["index"] == 2
    assert citations[1]["sourceType"] == "Consensus"


def test_publish_case_sync(tmp_path: Path) -> None:
    """Verify publish_case produces valid markdown with YAML frontmatter."""
    case_dir = tmp_path / "cases" / "MU-2026-09-18-001"
    case_dir.mkdir(parents=True)
    web_dir = tmp_path / "web"
    web_dir.mkdir(parents=True)

    article_text = """# DRAM Margin Warning: The $30B Micron CapEx Trap

Micron is reporting recovering margins [1].

## Primary Sources & Regulatory Receipts
- [1] Form 10-K FY2024: Accession 0000723125-24-000075 - https://www.sec.gov
"""
    (case_dir / "article.md").write_text(article_text, encoding="utf-8")

    inv_data = {
        "ticker": "MU",
        "as_of": "2026-09-18",
        "thesis": "Forensic Accounting Warning",
        "valuation": {"implied_growth_rate": 0.142, "fair_value": 78.50},
        "publication_readiness": {
            "passed": True,
            "status": "publishable",
            "reasons": [],
            "allowed_artifacts": ["article", "video", "publish"],
        },
        "citation_cards": [
            {
                "index": 1,
                "source_type": "SEC Filing",
                "title": "Form 10-K FY2024",
                "url": "https://www.sec.gov",
                "accession": "0000723125-24-000075",
                "filing_date": "2024-10-04",
                "facts": ["Recovering margins"],
                "quotes": [],
            }
        ],
    }
    (case_dir / "investigation.json").write_text(json.dumps(inv_data), encoding="utf-8")

    res = publish_case(
        case_dir=case_dir,
        web_root=web_dir,
        youtube_upload=False,
        deploy=False,
    )

    assert res.target_mdx_path.exists()
    content = res.target_mdx_path.read_text(encoding="utf-8")
    assert "caseId: MU-2026-09-18-001" in content
    assert "ticker: MU" in content
    assert "reverseDcfImpliedGrowth: '14.2%'" in content or 'reverseDcfImpliedGrowth: "14.2%"' in content or "14.2%" in content
    assert "targetValuation: '$78.50'" in content or 'targetValuation: "$78.50"' in content or "$78.50" in content
    assert "citations:" in content
    # Static text bibliography is stripped for web articles to avoid duplication with <FinancialReceipts />
    assert "## Primary Sources & Regulatory Receipts" not in content


def test_publish_case_blocked_without_readiness(tmp_path: Path) -> None:
    """Cases with blocked or missing publication readiness are rejected before writing."""
    case_dir = tmp_path / "cases" / "BLOCKED-2026-09-18-001"
    case_dir.mkdir(parents=True)
    web_dir = tmp_path / "web"
    web_dir.mkdir(parents=True)

    (case_dir / "article.md").write_text("# Title\nSome content [1].", encoding="utf-8")
    inv_data = {
        "ticker": "BLK",
        "publication_readiness": {
            "passed": False,
            "status": "blocked",
            "reasons": ["accounting_gate did not pass"],
        },
        "citation_cards": [{"index": 1, "title": "SEC 10-K", "url": "https://sec.gov"}],
    }
    (case_dir / "investigation.json").write_text(json.dumps(inv_data), encoding="utf-8")

    with pytest.raises(ValueError, match="blocked from publication"):
        publish_case(case_dir=case_dir, web_root=web_dir, youtube_upload=False, deploy=False)


def test_publish_case_blocked_with_invalid_citations(tmp_path: Path) -> None:
    """Cases with dangling or uncited claims in article.md are rejected."""
    case_dir = tmp_path / "cases" / "INVALID-2026-09-18-001"
    case_dir.mkdir(parents=True)
    web_dir = tmp_path / "web"
    web_dir.mkdir(parents=True)

    # Article cites [99] which is not in citation_cards
    (case_dir / "article.md").write_text("# Title\nDangling claim [99].", encoding="utf-8")
    inv_data = {
        "ticker": "INV",
        "publication_readiness": {"passed": True, "status": "publishable", "reasons": []},
        "citation_cards": [{"index": 1, "title": "SEC 10-K", "url": "https://sec.gov"}],
    }
    (case_dir / "investigation.json").write_text(json.dumps(inv_data), encoding="utf-8")

    with pytest.raises(ValueError, match="article failed citation validation"):
        publish_case(case_dir=case_dir, web_root=web_dir, youtube_upload=False, deploy=False)


def test_publish_case_ignores_appended_bibliography_entries(tmp_path: Path) -> None:
    """Publishing must not fail on the appended bibliography, whose entries carry no [n] tags."""
    case_dir = tmp_path / "cases" / "BIBLIO-2026-09-28-001"
    case_dir.mkdir(parents=True)
    web_dir = tmp_path / "web"
    web_dir.mkdir(parents=True)

    article_text = """# Turnaround Forensics

Free cash flow turned positive in Q2 [1].

## Primary Sources & Regulatory Receipts

1. **U.S. Securities & Exchange Commission (SEC) — Official XBRL Financial Statements ($INTC)** (SEC Accession `sec_xbrl` | [Official Source](https://www.sec.gov))
2. **Wall Street Consensus Aggregator & Broker Estimates Archive ($INTC)** ([Official Source](https://finance.yahoo.com))
"""
    (case_dir / "article.md").write_text(article_text, encoding="utf-8")
    inv_data = {
        "ticker": "BIBLIO",
        "as_of": "2026-09-28",
        "thesis": "Bibliography regression",
        "publication_readiness": {
            "passed": True,
            "status": "publishable",
            "reasons": [],
            "allowed_artifacts": ["article", "video", "publish"],
        },
        "citation_cards": [
            {"index": 1, "source_type": "SEC Filing", "title": "Form 10-Q", "url": "https://www.sec.gov"},
        ],
    }
    (case_dir / "investigation.json").write_text(json.dumps(inv_data), encoding="utf-8")

    res = publish_case(case_dir=case_dir, web_root=web_dir, youtube_upload=False, deploy=False)
    assert res.target_mdx_path.exists()
    content = res.target_mdx_path.read_text(encoding="utf-8")
    assert "citations:" in content
    # Static text bibliography is stripped from web body to avoid duplicate citations
    assert "## Primary Sources & Regulatory Receipts" not in content


def test_publish_case_multi_candidate_hydration(tmp_path: Path) -> None:
    """Verify that multi-candidate screening runs resolve target ticker and hydrate valuation metrics."""
    case_dir = tmp_path / "cases" / "RESEARCH-2026-09-30-004"
    case_dir.mkdir(parents=True)
    web_dir = tmp_path / "web"
    web_dir.mkdir(parents=True)

    article_text = """---
primary_ticker: ADBE
thesis: Forensic Accounting & Reverse DCF Analysis
verdict: Approved Long
---
# The Ghost in the Canvas: Why the Street Got Adobe Backwards

Adobe continues to expand enterprise revenue [1].

## Primary Sources & Regulatory Receipts
1. **SEC Form 10-Q** (Accession `sec_xbrl` | [Official Source](https://www.sec.gov))
"""
    (case_dir / "article.md").write_text(article_text, encoding="utf-8")
    inv_data = {
        "ticker": "",
        "as_of": "2026-10-01",
        "publication_readiness": {
            "passed": True,
            "status": "publishable",
            "reasons": [],
            "allowed_artifacts": ["article", "video", "publish"],
        },
        "candidates": {
            "cand_adbe": {
                "ticker": "ADBE",
                "company": "Adobe Inc.",
                "quant_report": {
                    "valuation": {
                        "reverse_dcf": {
                            "implied_growth_pct": "-4.42%",
                            "implied_fcf_growth_rate": -0.0442,
                        },
                        "fair_value_range": {
                            "base": 356.58,
                            "blended_base": 356.58,
                        },
                    }
                },
                "forensic_report": {"verdict": "Normal"},
            }
        },
        "citation_cards": [
            {"index": 1, "source_type": "SEC Filing", "title": "SEC Form 10-Q", "url": "https://www.sec.gov"},
        ],
    }
    (case_dir / "investigation.json").write_text(json.dumps(inv_data), encoding="utf-8")

    res = publish_case(case_dir=case_dir, web_root=web_dir, youtube_upload=False, deploy=False)
    assert res.target_mdx_path.exists()
    content = res.target_mdx_path.read_text(encoding="utf-8")

    assert "ticker: ADBE" in content
    assert "reverseDcfImpliedGrowth: '-4.42%'" in content or 'reverseDcfImpliedGrowth: "-4.42%"' in content or "-4.42%" in content
    assert "targetValuation: '$356.58'" in content or 'targetValuation: "$356.58"' in content or "$356.58" in content
    assert "beneishMScore: Normal" in content
    assert "## Primary Sources & Regulatory Receipts" not in content

