"""Tests for media generation: cited forensic article and Faceless reel script."""
import json
from unittest.mock import MagicMock
import pytest
from langchain_core.messages import AIMessage

from app.agent.state import ResearchRequest, create_initial_state
from app.agent.media import (
    CitationCard,
    MediaPackage,
    build_source_registry,
    format_source_registry_for_prompt,
    format_bibliography_markdown,
    generate_article_markdown,
    generate_media_package,
    generate_reel_script,
    validate_dialogue_json,
    PETER_VOICE_ID,
    STEWIE_VOICE_ID,
    RICK_VOICE_ID,
    MORTY_VOICE_ID,
)


def _valid_dialogue():
    return [
        {"index": 0, "voiceId": PETER_VOICE_ID, "text": "(shocked) You're saying RAM prices are surging?"},
        {"index": 1, "voiceId": STEWIE_VOICE_ID, "text": "(smirking) Yes, and Micron raised prices by 35%."},
        {"index": 2, "voiceId": PETER_VOICE_ID, "text": "(curious) But did Wall Street notice?"},
        {"index": 3, "voiceId": STEWIE_VOICE_ID, "text": "(laughing) No, consensus is flat. Check the audit below!"},
    ]


def test_validate_dialogue_json_valid():
    lines = _valid_dialogue()
    assert validate_dialogue_json(lines, character_pair="peter_stewie") is True


def test_validate_dialogue_json_rejects_non_alternating():
    lines = [
        {"index": 0, "voiceId": PETER_VOICE_ID, "text": "(shocked) Question 1"},
        {"index": 1, "voiceId": PETER_VOICE_ID, "text": "(shocked) Question 2"},
    ]
    with pytest.raises(ValueError, match="alternate"):
        validate_dialogue_json(lines, character_pair="peter_stewie")


def test_validate_dialogue_json_rejects_missing_emotion_tag():
    lines = [
        {"index": 0, "voiceId": PETER_VOICE_ID, "text": "No emotion tag here."},
        {"index": 1, "voiceId": STEWIE_VOICE_ID, "text": "(smirking) Answer."},
    ]
    with pytest.raises(ValueError, match="emotion"):
        validate_dialogue_json(lines, character_pair="peter_stewie")


def test_build_source_registry_extracts_and_indexes_sources():
    """Verify build_source_registry extracts SEC, consensus, and market data into indexed CitationCards."""
    req = ResearchRequest(query="Investigate NVDA", ticker="NVDA", company="NVIDIA Corp")
    state = create_initial_state(req, case_id="case_nvda")

    state["sec_financials"] = {
        "status": "ok",
        "provider": "0001045810-26-000045",
        "periods": ["2026Q3", "2026Q2"],
        "revenue": {"2026Q3": 35000000000.0},
        "gross_margin_pct": {"2026Q3": 0.75},
        "ttm_fcf": 45000000000.0,
    }
    state["consensus_snapshot"] = {
        "target_mean_price": 180.0,
        "target_low_price": 120.0,
        "target_high_price": 240.0,
        "ratings": {"buy": 35, "hold": 5, "sell": 1},
    }
    state["market_context"] = {
        "quote": {"price": 140.50, "market_cap": 3400000000000.0, "as_of": "2026-09-18"},
        "volume_ratio_20d": {"value": 1.25},
    }
    state["evidence"] = [
        {
            "form": "10-Q",
            "accession": "0001045810-26-000045",
            "source_url": "https://www.sec.gov/edgar/nvda-10q.htm",
            "quote": "Data center compute revenue grew 150% YoY.",
            "filing_date": "2026-08-28",
        }
    ]

    cards = build_source_registry(state)
    assert len(cards) >= 4

    # Card [1] is SEC financials
    assert cards[0].index == 1
    assert cards[0].tag == "[1]"
    assert cards[0].source_type == "SEC Filing"
    assert any("Revenue: $35.00B" in f for f in cards[0].facts)
    assert any("75.0%" in f for f in cards[0].facts)

    # Card [2] is Consensus
    assert cards[1].index == 2
    assert cards[1].tag == "[2]"
    assert cards[1].source_type == "Consensus"
    assert any("Mean $180.00" in f for f in cards[1].facts)

    # Card [3] is Market Data
    assert cards[2].index == 3
    assert cards[2].tag == "[3]"
    assert cards[2].source_type == "Market Data"
    assert any("$140.50" in f for f in cards[2].facts)

    # Card [4] is SEC Evidence Excerpt
    assert cards[3].index == 4
    assert cards[3].tag == "[4]"
    assert "Data center compute" in cards[3].quotes[0]

    # Verify prompt text format
    prompt_text = format_source_registry_for_prompt(cards)
    assert "[1] **U.S. Securities & Exchange Commission" in prompt_text
    assert "[2] **Wall Street Consensus" in prompt_text

    # Verify bibliography format
    biblio_text = format_bibliography_markdown(cards)
    assert "## Primary Sources & Regulatory Receipts" in biblio_text
    assert "1. **U.S. Securities & Exchange Commission" in biblio_text
    assert "2. **Wall Street Consensus" in biblio_text


class FakeArticleModel:
    """Mock model returning article text with bracketed citations."""

    def invoke(self, messages):
        return AIMessage(
            content="""# The Memory Boom Is Real — And Micron's 10-Q Proves Who Wins

**Bottom Line**: Memory shortages are driving unprecedented pricing power and gross margin expansion [1].

## The Wall Street Expectation Gap
Consensus targets average $1,513.11 with 49 analysts covering the stock [2].

## SEC XBRL Margins & Financial Trajectory
According to official SEC filings [1], gross margins expanded to 36.2%. The current share price trades at $927.60 [3].
"""
        )


class FakeReelModel:
    """Mock model returning reel dialogue JSON and caption."""

    def invoke(self, messages):
        dialogue_text = json.dumps(_valid_dialogue())
        return AIMessage(
            content=f"""```json
{dialogue_text}
```

CAPTION:
DDR5 RAM is disappearing from shelves, but Wall Street is sleeping on the real winner. 🚨 Full SEC audit in bio. #stocks #investing #DDR5 #micron"""
        )


class FakeMediaModel:
    """Mock model returning article and then dialogue JSON (legacy 2-call pattern)."""

    def __init__(self):
        self.call_count = 0

    def invoke(self, messages):
        self.call_count += 1
        if self.call_count == 1:
            return FakeArticleModel().invoke(messages)
        else:
            return FakeReelModel().invoke(messages)


def test_generate_article_markdown():
    """Verify generate_article_markdown passes pre-indexed cards and appends verified bibliography."""
    req = ResearchRequest(query="Investigate MU DDR5 boom", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu_article")
    state["sec_financials"] = {
        "status": "ok",
        "provider": "0001193125-26-123456",
        "periods": ["2026Q3"],
        "revenue": {"2026Q3": 34800000000.0},
        "gross_margin_pct": {"2026Q3": 0.362},
    }
    state["consensus_snapshot"] = {
        "target_mean_price": 1513.11,
        "ratings": {"buy": 36, "hold": 4},
    }
    state["market_context"] = {
        "quote": {"price": 927.60, "market_cap": 1048000000000.0},
    }
    state["evidence"] = [
        {
            "form": "10-Q",
            "accession": "0001193125-26-123456",
            "source_url": "https://www.sec.gov/123",
            "quote": "Gross margin expanded to 36.2%",
            "filing_date": "2026-09-01",
        }
    ]
    memo_md = "# Research Memo\nGross margin expanded to 36.2% [SEC 10-Q]."

    article = generate_article_markdown(memo_md, state, model=FakeArticleModel())

    # In-text citation tags present
    assert "[1]" in article
    assert "[2]" in article
    assert "[3]" in article

    # Verified deterministic bibliography appended by Python
    assert "## Primary Sources & Regulatory Receipts" in article
    assert "SEC Accession `0001193125-26-123456`" in article
    assert "https://finance.yahoo.com/quote/MU" in article


def test_build_source_registry_multi_candidate():
    """Verify build_source_registry creates distinct cards for all candidates in a ranking run."""
    req = ResearchRequest(query="Compare NVDA and GOOGL", ticker=None, requested_ranking_count=2)
    state = create_initial_state(req, case_id="multi_cards")

    state["candidates"] = {
        "cand_nvda": {
            "candidate_id": "cand_nvda",
            "ticker": "NVDA",
            "company": "NVIDIA Corp",
            "sec_financials": {
                "status": "ok",
                "provider": "0001045810-26-000045",
                "periods": ["2026Q3"],
                "revenue": {"2026Q3": 35000000000.0},
            },
            "market_context": {"quote": {"price": 140.0}},
        },
        "cand_googl": {
            "candidate_id": "cand_googl",
            "ticker": "GOOGL",
            "company": "Alphabet Inc",
            "sec_financials": {
                "status": "ok",
                "provider": "0001652044-26-000048",
                "periods": ["2026Q2"],
                "revenue": {"2026Q2": 95000000000.0},
            },
            "market_context": {"quote": {"price": 180.0}},
        },
    }

    cards = build_source_registry(state)
    card_titles = [c.title for c in cards]

    # Both NVDA and GOOGL must have their own citation cards
    assert any("($NVDA)" in t for t in card_titles)
    assert any("($GOOGL)" in t for t in card_titles)


def test_generate_article_markdown_multi_candidate():
    """Verify generate_article_markdown builds comparative prompt mentioning the candidate cohort."""
    class CapturePromptModel:
        def __init__(self):
            self.captured_prompt = ""
        def invoke(self, messages):
            self.captured_prompt = messages[-1].content
            return AIMessage(content="# Top Tech Allocations: NVDA and GOOGL\nComparison text with [1] and [2].")

    req = ResearchRequest(query="Find 2 best tech stocks", ticker=None, requested_ranking_count=2)
    state = create_initial_state(req, case_id="multi_art")
    state["candidates"] = {
        "cand_nvda": {"candidate_id": "cand_nvda", "ticker": "NVDA", "sec_financials": {"status": "ok", "periods": ["2026Q3"]}},
        "cand_googl": {"candidate_id": "cand_googl", "ticker": "GOOGL", "sec_financials": {"status": "ok", "periods": ["2026Q2"]}},
    }
    memo_md = "# Deep Research Report\nTop 2: NVDA and GOOGL."

    model = CapturePromptModel()
    article = generate_article_markdown(memo_md, state, model=model)

    assert "$NVDA" in model.captured_prompt
    assert "$GOOGL" in model.captured_prompt
    assert "comparative research article" in model.captured_prompt
    assert "Top Ranked" in model.captured_prompt


def test_generate_reel_script_alternating_dialogue():
    """Verify generate_reel_script produces alternating Peter/Stewie dialogue."""
    article = "# Test Article\nSome content about stocks."
    dialogue_json, reel_script, caption = generate_reel_script(
        article, model=FakeReelModel(), character_pair="peter_stewie",
    )
    assert len(dialogue_json) == 4
    assert dialogue_json[0]["voiceId"] == PETER_VOICE_ID
    assert dialogue_json[1]["voiceId"] == STEWIE_VOICE_ID
    assert "(shocked)" in dialogue_json[0]["text"]
    assert "#stocks" in caption
    assert "[Speaker A]:" in reel_script


def test_generate_reel_script_safe_fallback():
    """Verify broken dialogue falls back to safe neutral lines."""
    class BrokenModel:
        def invoke(self, messages):
            return AIMessage(content="Not valid json or dialogue format.")

    dialogue_json, reel_script, caption = generate_reel_script(
        "Article content.", model=BrokenModel(), character_pair="peter_stewie",
    )
    assert len(dialogue_json) == 4
    full_text = " ".join(line["text"] for line in dialogue_json)
    assert "gross margin expansion" not in full_text.lower()


def test_generate_media_package_success():
    req = ResearchRequest(query="Investigate MU DDR5 boom", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu_media")
    state["evidence"] = [
        {
            "form": "10-Q",
            "accession": "0001193125-26-123456",
            "source_url": "https://www.sec.gov/123",
            "quote": "Gross margin expanded to 36%",
            "filing_date": "2026-09-01",
        }
    ]

    model = FakeMediaModel()
    pkg = generate_media_package(state, model=model, character_pair="peter_stewie")

    assert isinstance(pkg, MediaPackage)
    assert pkg.ticker == "MU"
    assert "[1]" in pkg.article_markdown
    assert "0001193125-26-123456" in pkg.article_markdown
    assert len(pkg.dialogue_json) == 4
    assert pkg.dialogue_json[0]["voiceId"] == PETER_VOICE_ID
    assert "(shocked)" in pkg.dialogue_json[0]["text"]
    assert "#stocks" in pkg.caption_text


def test_generate_media_package_safe_fallback_on_parse_error():
    """Verify malformed dialogue generation uses neutral fallback without hallucinated facts."""
    class BrokenDialogueModel:
        def __init__(self):
            self.call_count = 0

        def invoke(self, messages):
            self.call_count += 1
            if self.call_count == 1:
                return AIMessage(content="# Article\nNo claims.")
            return AIMessage(content="Not valid json or dialogue format.")

    req = ResearchRequest(query="Investigate XYZ", ticker="XYZ")
    state = create_initial_state(req, case_id="case_xyz_fallback")
    state["evidence"] = [{"source_url": "https://www.sec.gov/example", "quote": "Primary filing excerpt."}]
    pkg = generate_media_package(state, model=BrokenDialogueModel())

    assert len(pkg.dialogue_json) == 4
    full_text = " ".join(line["text"] for line in pkg.dialogue_json)
    assert "gross margin expansion" not in full_text.lower()
    assert "consumer demand surged" not in full_text.lower()
