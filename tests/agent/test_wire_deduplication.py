"""Tests for PR wire syndication shingle deduplication in build_evidence_packet."""
import pytest
from app.agent.grounded_synthesis import (
    _shingle_set,
    _jaccard_similarity,
    build_evidence_packet,
)


def test_shingle_set_and_jaccard_similarity():
    """Verify 5-word shingle generation and Jaccard similarity threshold."""
    text1 = "Micron Technology begins volume production of 24GB 8-High HBM3E memory for AI."
    text2 = "Micron Technology begins volume production of 24GB 8-High HBM3E memory for AI."
    text3 = "Micron Technology reported quarterly revenue of 13.6 billion dollars beating expectations."

    s1 = _shingle_set(text1, n=5)
    s2 = _shingle_set(text2, n=5)
    s3 = _shingle_set(text3, n=5)

    assert len(s1) > 0
    assert _jaccard_similarity(s1, s2) == 1.0
    assert _jaccard_similarity(s1, s3) < 0.20


def test_build_evidence_packet_collapses_wire_reposts():
    """Verify identical PR wire quotes across different syndication outlets are collapsed into 1 evidence item."""
    wire_quote_1 = (
        "Micron Technology today announced it has begun volume production of its HBM3E (High Bandwidth Memory 3E) "
        "semiconductor solution with 24GB capacity, offering superior performance and energy efficiency for NVIDIA H200."
    )
    wire_quote_2 = (
        "Micron Technology today announced it has begun volume production of its HBM3E (High Bandwidth Memory 3E) "
        "semiconductor solution with 24GB capacity, offering superior performance and energy efficiency for NVIDIA H200."
    )
    different_quote = (
        "Form 10-Q Item 2: Capital expenditures reached 5.39 billion dollars representing 39.5 percent of net sales."
    )

    state = {
        "evidence": [
            {
                "excerpt_id": "ev_pr_newswire_01",
                "source": "PR_Newswire",
                "quote": wire_quote_1,
                "source_url": "https://prnewswire.com/micron-hbm3e",
            },
            {
                "excerpt_id": "ev_yahoo_reprint_02",
                "source": "Yahoo_Finance",
                "quote": wire_quote_2,
                "source_url": "https://finance.yahoo.com/news/micron-hbm3e-reprint",
            },
            {
                "excerpt_id": "ev_sec_10q_03",
                "source": "SEC_10Q",
                "quote": different_quote,
                "source_url": "https://sec.gov/Archives/edgar/data/723125/000072312526000010/mu-20260226.htm",
            },
        ],
    }

    packet = build_evidence_packet(state)

    # 3 raw evidence quotes should collapse to 2 items (the duplicate wire quote was deduplicated)
    assert packet["count"] == 2
    assert len(packet["items"]) == 2

    pr_item = packet["items"]["ev_pr_newswire_01"]
    assert pr_item["source_type"] == "PR_Newswire"
    assert "[Syndicated PR/Wire]:" in pr_item["fact_summary"]
    # Verified that the syndicated reprint URL was recorded on the primary issuer record
    assert "https://finance.yahoo.com/news/micron-hbm3e-reprint" in pr_item["locator"]
    assert "https://prnewswire.com/micron-hbm3e" in pr_item["locator"]

    sec_item = packet["items"]["ev_sec_10q_03"]
    assert sec_item["source_type"] == "SEC_10Q"
    assert "[Syndicated PR/Wire]:" not in sec_item["fact_summary"]
