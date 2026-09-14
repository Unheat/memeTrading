"""Media generation module: publication-grade cited forensic article and Faceless video reel script.

Adapts Faceless dialogue JSON schema (dialogue-json-schema.md) and financial research formats.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import InvestigationState

logger = logging.getLogger(__name__)

# Faceless character voice IDs (from faceless/skills/faceless/scripts/generate-audio.mjs)
PETER_VOICE_ID = "e34b4e061b874623a08f41e5c4fecfb9"
STEWIE_VOICE_ID = "fdffd3722cd040fcb3f95eec5a7f29f3"
RICK_VOICE_ID = "d2e75a3e3fd6419893057c02a375a113"
MORTY_VOICE_ID = "3d445d095ba04681bcba7177faedf55a"

VALID_EMOTION_PATTERN = re.compile(r"^\([a-zA-Z\s_-]+\)\s+", re.IGNORECASE)

MEDIA_ARTICLE_SYSTEM_PROMPT = """You are a senior financial investigative journalist and former hedge fund partner.
Your mission is to write a deeply cited, publication-grade forensic research article (Substack / Institutional Investment Note style).

RULES FOR CITATIONS:
1. Every factual statement or financial number MUST cite a primary source using numbered brackets: [1], [2], [3].
2. The bottom of the article MUST include a "## Primary Sources & Regulatory Receipts" section mapping every number to its exact SEC filing accession number, form type, filing date, and URL.
3. Include clear Markdown comparison tables for:
   - SEC XBRL Margins & Financial Trajectory
   - Wall Street Consensus vs Reality (The Expectation Gap)
4. Highlight the 2 Quantitative Numeric Kill Criteria formulated by the Adversarial Red Team.
"""

MEDIA_REEL_SYSTEM_PROMPT = """You are a master viral finance creator.
Your job is to turn this research into a hilarious, punchy, 60–75 second two-person dialogue reel script in the exact comedic style of {cast_name}.

5-BEAT STRUCTURE:
1. The Hook (0–10s): Shocking counter-intuitive opening statement.
2. The Scuttlebutt Signal (10–25s): Ground consumer/developer shortages or volume spikes.
3. The SEC / Corporate Mechanism (25–45s): How the company monetizes it (gross margins jumping, pricing power).
4. The Expectation Gap (45–60s): Why Wall Street consensus models haven't priced it in yet.
5. The Handoff (60–75s): Punchline pointing the viewer directly to the cited audit below.

{persona_instructions}

VOICE & SCHEMA REQUIREMENTS:
- Character 1 (Speaker A): voiceId "{first_voice}"
- Character 2 (Speaker B): voiceId "{second_voice}"
- Speakers must strictly alternate (A, B, A, B...).
- Every spoken line MUST start with an emotion tag: (shocked), (smirking), (excited), (deadpan), (laughing), (confused), (skeptical), (confident).
- The final line must be spoken by Character 2 directing the viewer to the audit receipts below.

OUTPUT FORMAT:
Return strictly a valid JSON array of objects inside a ```json code fence:
```json
[
  { "index": 0, "voiceId": "{first_voice}", "text": "(shocked) Opening line..." },
  { "index": 1, "voiceId": "{second_voice}", "text": "(smirking) Second line..." }
]
```
Followed by:
CAPTION:
<Instagram / TikTok hook and caption with hashtags>
"""


@dataclass(frozen=True)
class MediaPackage:
    """Synchronized video reel script and cited research article."""

    ticker: str
    article_markdown: str
    dialogue_json: list[dict[str, Any]]
    reel_script_text: str
    caption_text: str


def validate_dialogue_json(lines: list[dict[str, Any]], character_pair: str = "peter_stewie") -> bool:
    """Validate dialogue list against Faceless schema rules."""
    if not isinstance(lines, list) or len(lines) == 0:
        raise ValueError("Dialogue JSON must be a non-empty list.")

    allowed_pair = (
        (PETER_VOICE_ID, STEWIE_VOICE_ID)
        if character_pair == "peter_stewie"
        else (RICK_VOICE_ID, MORTY_VOICE_ID)
    )

    for idx, line in enumerate(lines):
        if line.get("index") != idx:
            raise ValueError(f"Dialogue line {idx} has invalid or non-sequential index.")
        voice_id = line.get("voiceId")
        if voice_id not in allowed_pair:
            raise ValueError(f"Dialogue line {idx} has invalid voiceId: {voice_id}")
        if idx > 0 and voice_id == lines[idx - 1].get("voiceId"):
            raise ValueError(f"Dialogue line {idx} does not alternate speakers.")
        text = str(line.get("text") or "").strip()
        if not text:
            raise ValueError(f"Dialogue line {idx} text cannot be empty.")
        if not VALID_EMOTION_PATTERN.match(text):
            raise ValueError(f"Dialogue line {idx} must start with an emotion tag in parentheses, e.g. (shocked).")

    return True


def generate_media_package(
    state: InvestigationState,
    model: Any,
    character_pair: str = "peter_stewie",
    reel_temperature: float = 0.4,
) -> MediaPackage:
    """Generate the cited forensic article and Faceless video reel package.

    :param state: InvestigationState with audited facts and consensus.
    :param model: LLM model instance.
    :param character_pair: 'peter_stewie' or 'rick_morty'.
    :param reel_temperature: Higher temperature for comedic banter generation (default 0.4).
    :returns: MediaPackage with article.md and dialogue.json.
    """
    ticker = state.get("ticker") or "UNKNOWN"
    company = state.get("company") or ""
    evidence = state.get("evidence", [])
    contradictions = state.get("contradictions", [])
    market = state.get("market_context") or {}
    consensus = state.get("consensus_snapshot") or {}
    adversarial = state.get("adversarial_report")
    ic_verdict = state.get("ic_verdict")

    if character_pair == "peter_stewie":
        first_voice, second_voice = PETER_VOICE_ID, STEWIE_VOICE_ID
        cast_name = "Family Guy's Peter Griffin and Stewie Griffin"
        persona_instructions = f"""CHARACTER PERSONAS (Peter & Stewie from Family Guy):
- Speaker A (Peter Griffin - voiceId "{first_voice}"): Clueless, gullible, impulsive everyday retail investor. Speaks casually, easily distracted, confuses financial terms, obsessed with viral internet hype.
- Speaker B (Stewie Griffin - voiceId "{second_voice}"): Smug, hyper-articulate, condescending British genius. Speaks with sophisticated vocabulary, treats Peter like an absolute idiot, and drops brutal, verifiable SEC filing facts, gross margin jumps, and valuation reality."""
    else:
        first_voice, second_voice = RICK_VOICE_ID, MORTY_VOICE_ID
        cast_name = "Rick and Morty"
        persona_instructions = f"""CHARACTER PERSONAS (Rick & Morty):
- Speaker A (Morty Smith - voiceId "{first_voice}"): Anxious, stuttering, nervous everyday guy terrified of losing money on the stock market.
- Speaker B (Rick Sanchez - voiceId "{second_voice}"): Cynical, arrogant, reckless rogue genius who sees right through Wall Street consensus nonsense and explains the supply-chain arbitrage with cold mathematical certainty."""

    context_payload = json.dumps(
        {
            "ticker": ticker,
            "company": company,
            "trigger": state.get("trigger"),
            "root_claims": state.get("root_claims"),
            "verified_evidence": evidence,
            "contradictions": contradictions,
            "market_context": market,
            "consensus_snapshot": consensus,
            "adversarial_kill_triggers": adversarial.numeric_kill_criteria if adversarial else [],
            "ic_verdict": ic_verdict.to_dict() if ic_verdict else None,
        },
        indent=2,
    )

    # 1. Generate Cited Forensic Article
    article_prompt = f"""Write an institutional, deeply cited forensic research article for ${ticker} ({company}).

Investigated Facts & SEC Evidence:
```json
{context_payload}
```
"""
    article_res = model.invoke([
        SystemMessage(content=MEDIA_ARTICLE_SYSTEM_PROMPT),
        HumanMessage(content=article_prompt),
    ])
    article_md = getattr(article_res, "content", "")

    # 2. Generate Two-Person Dialogue Script & Caption
    reel_sys_prompt = (
        MEDIA_REEL_SYSTEM_PROMPT
        .replace("{cast_name}", cast_name)
        .replace("{persona_instructions}", persona_instructions)
        .replace("{first_voice}", first_voice)
        .replace("{second_voice}", second_voice)
    )
    reel_prompt = f"""Create the 60–75 second viral dialogue reel for ${ticker} based on these verified facts:
```json
{context_payload}
```
"""
    reel_model = (
        model.bind(temperature=reel_temperature)
        if hasattr(model, "bind") and reel_temperature is not None
        else model
    )
    reel_res = reel_model.invoke([
        SystemMessage(content=reel_sys_prompt),
        HumanMessage(content=reel_prompt),
    ])
    reel_raw = getattr(reel_res, "content", "")

    # Parse JSON block
    dialogue_lines: list[dict[str, Any]] = []
    caption_text = f"The hidden financial truth behind ${ticker}. 🚨 Read the full verified SEC audit in bio. #investing #stocks #finance"

    try:
        if "```json" in reel_raw:
            json_part = reel_raw.split("```json")[1].split("```")[0].strip()
            dialogue_lines = json.loads(json_part)
        elif "```" in reel_raw:
            json_part = reel_raw.split("```")[1].split("```")[0].strip()
            dialogue_lines = json.loads(json_part)

        if "CAPTION:" in reel_raw:
            caption_text = reel_raw.split("CAPTION:")[1].strip()

        validate_dialogue_json(dialogue_lines, character_pair=character_pair)
    except Exception as exc:
        logger.warning("Dialogue JSON generation error for %s: %s; using safe fallback", ticker, exc)
        dialogue_lines = [
            {"index": 0, "voiceId": first_voice, "text": f"(confused) What did the forensic research find on ${ticker}?"},
            {"index": 1, "voiceId": second_voice, "text": f"(confident) We pulled the official SEC filings and consensus data to audit ${ticker}."},
            {"index": 2, "voiceId": first_voice, "text": "(skeptical) Are the claims verified by primary regulatory sources?"},
            {"index": 3, "voiceId": second_voice, "text": f"(deadpan) Check the complete verified memo and source receipts on ${ticker} below."},
        ]

    # Render readable transcript
    script_lines = []
    for line in dialogue_lines:
        spk = "Speaker A" if line.get("voiceId") == first_voice else "Speaker B"
        script_lines.append(f"[{spk}]: {line.get('text')}")
    reel_script_text = "\n\n".join(script_lines)

    return MediaPackage(
        ticker=ticker,
        article_markdown=article_md,
        dialogue_json=dialogue_lines,
        reel_script_text=reel_script_text,
        caption_text=caption_text,
    )
