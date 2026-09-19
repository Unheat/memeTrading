"""Tests for media generation: cited forensic article and Faceless reel script."""
import json
from unittest.mock import MagicMock
import pytest
from langchain_core.messages import AIMessage

from app.agent.state import ResearchRequest, create_initial_state
from app.agent.media import (
    MediaPackage,
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


class FakeArticleModel:
    """Mock model returning article text."""

    def invoke(self, messages):
        return AIMessage(
            content="""# The DDR5 Shortage Is Real — And Micron's 10-Q Proves Who Wins

**Bottom Line**: Retail memory shortages are translating into expanding margins [1].

## The Scuttlebutt Signal
Forums reported empty shelves across MicroCenter [2].

## SEC Audit & Receipts
According to Micron's Form 10-Q [1], gross margins expanded to 36%.

## Primary Sources & Regulatory Receipts
[1] Form 10-Q, Accession 0001193125-26-123456, https://www.sec.gov/Archives/edgar/data/723125/000119312526123456/doc.htm
[2] Reddit r/buildapc thread on retail stockouts"""
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
    """Verify generate_article_markdown passes memo to model and returns cited article."""
    req = ResearchRequest(query="Investigate MU DDR5 boom", ticker="MU", company="Micron")
    state = create_initial_state(req, case_id="case_mu_article")
    state["evidence"] = [
        {
            "form": "10-Q",
            "accession": "0001193125-26-123456",
            "source_url": "https://www.sec.gov/123",
            "quote": "Gross margin expanded to 36%",
            "filing_date": "2026-09-01",
        }
    ]
    memo_md = "# Research Memo\nGross margin expanded to 36% [SEC 10-Q]."

    article = generate_article_markdown(memo_md, state, model=FakeArticleModel())
    assert "[1]" in article
    assert "0001193125-26-123456" in article


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
