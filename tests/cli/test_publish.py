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
    assert "## Primary Sources & Regulatory Receipts" in content
