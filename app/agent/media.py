"""Media generation module: publication-grade cited forensic article and Faceless video reel script.

Adapts Faceless dialogue JSON schema (dialogue-json-schema.md) and financial research formats.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.state import InvestigationState

logger = logging.getLogger(__name__)

# Faceless character voice IDs (from faceless/skills/faceless/scripts/generate-audio.mjs)
PETER_VOICE_ID = "a84d19016bc34098b3c89d78f9299e33"
STEWIE_VOICE_ID = "e91c4f5974f149478a35affe820d02ac"
RICK_VOICE_ID = "d2e75a3e3fd6419893057c02a375a113"
MORTY_VOICE_ID = "3d445d095ba04681bcba7177faedf55a"

VALID_EMOTION_PATTERN = re.compile(r"^\([a-zA-Z\s_-]+\)\s+", re.IGNORECASE)

# Maximum number of FactCards to include in article context to avoid token bloat
MAX_FACT_CARDS_IN_CONTEXT = 30

MEDIA_ARTICLE_SYSTEM_PROMPT = """You are a senior financial investigative journalist and former hedge fund partner.
Your mission is to write a deeply cited, publication-grade forensic research article (Substack / Institutional Investment Note style).

RULES FOR CITATIONS:
1. Every factual statement or financial number MUST cite a primary source using numbered brackets: [1], [2], [3].
2. The bottom of the article MUST include a "## Primary Sources & Regulatory Receipts" section mapping every number to its exact SEC filing accession number, form type, filing date, and URL.
3. Include clear Markdown comparison tables for:
   - SEC XBRL Margins & Financial Trajectory
   - Wall Street Consensus vs Reality (The Expectation Gap)
4. Highlight the 2 Quantitative Numeric Kill Criteria formulated by the Adversarial Red Team.

IMPORTANT: You MUST only use facts, numbers, and citations that appear in the provided research memo and evidence receipts below.
Do NOT fabricate, guess, or hallucinate any accession numbers, financial figures, filing dates, or URLs.
If a specific number or citation is not present in the provided context, state that it was not available rather than inventing one.
"""

MEDIA_REEL_SYSTEM_PROMPT = """You are a master viral finance creator.
Your job is to turn this research article into a hilarious, punchy, 60–75 second two-person dialogue reel script in the exact comedic style of {cast_name}.

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
  {{ "index": 0, "voiceId": "{first_voice}", "text": "(shocked) Opening line..." }},
  {{ "index": 1, "voiceId": "{second_voice}", "text": "(smirking) Second line..." }}
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


def _collect_evidence_receipts(state: InvestigationState) -> list[dict[str, Any]]:
    """Consolidate evidence citations from top-level state and all candidate workspaces.

    Args:
        state: Completed investigation state.

    Returns:
        Deduplicated list of evidence items with source_url and quote fields.
    """
    seen_urls: set[str] = set()
    receipts: list[dict[str, Any]] = []

    for item in state.get("evidence", []):
        if isinstance(item, Mapping) and item.get("source_url"):
            url = str(item["source_url"])
            if url not in seen_urls:
                seen_urls.add(url)
                receipts.append(dict(item))

    for cand in (state.get("candidates") or {}).values():
        if isinstance(cand, Mapping):
            for item in cand.get("evidence", []):
                if isinstance(item, Mapping) and item.get("source_url"):
                    url = str(item["source_url"])
                    if url not in seen_urls:
                        seen_urls.add(url)
                        receipts.append(dict(item))

    return receipts


def _collect_fact_cards(state: InvestigationState) -> list[dict[str, Any]]:
    """Collect FactCards from top-level state and candidate workspaces.

    Args:
        state: Completed investigation state.

    Returns:
        Deduplicated list of FactCards, capped at MAX_FACT_CARDS_IN_CONTEXT.
    """
    seen_ids: set[str] = set()
    cards: list[dict[str, Any]] = []

    for card in state.get("fact_cards", []):
        if isinstance(card, Mapping):
            fid = str(card.get("fact_id") or "")
            if fid and fid not in seen_ids:
                seen_ids.add(fid)
                cards.append(dict(card))

    for cand in (state.get("candidates") or {}).values():
        if isinstance(cand, Mapping):
            for card in cand.get("fact_cards", []):
                if isinstance(card, Mapping):
                    fid = str(card.get("fact_id") or "")
                    if fid and fid not in seen_ids:
                        seen_ids.add(fid)
                        cards.append(dict(card))

    return cards[:MAX_FACT_CARDS_IN_CONTEXT]


def validate_dialogue_json(lines: list[dict[str, Any]], character_pair: str = "peter_stewie") -> bool:
    """Validate dialogue list against Faceless schema rules.

    Args:
        lines: List of dialogue line dictionaries.
        character_pair: Which character duo to validate against.

    Returns:
        True if all validation rules pass.

    Raises:
        ValueError: If any dialogue line violates the Faceless schema.
    """
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


def generate_article_markdown(
    memo_markdown: str,
    state: InvestigationState,
    model: Any,
) -> str:
    """Generate a publication-grade cited Substack article from the finalized research memo.

    The article writer receives the fully rendered memo (ground truth) plus structured
    evidence receipts and FactCards. It transforms the technical research into an engaging
    publication article with bracketed [1], [2] citations.

    Args:
        memo_markdown: The finalized forensic research memo text.
        state: Completed investigation state for extracting evidence receipts.
        model: LLM model instance.

    Returns:
        Article markdown string with citations.
    """
    ticker = state.get("ticker") or "RESEARCH"
    company = state.get("company") or ""
    evidence_receipts = _collect_evidence_receipts(state)
    fact_cards = _collect_fact_cards(state)

    context_payload = json.dumps(
        {
            "ticker": ticker,
            "company": company,
            "evidence_receipts": evidence_receipts,
            "fact_cards": fact_cards,
            "sec_financials": state.get("sec_financials"),
            "consensus_snapshot": state.get("consensus_snapshot"),
            "market_context": state.get("market_context"),
        },
        indent=2,
        default=str,
    )

    article_prompt = f"""Write an institutional, deeply cited forensic research article for ${ticker} ({company}).

## Audited Research Memo (Ground Truth — cite only from this content)
```markdown
{memo_markdown}
```

## Verified Evidence Receipts & Financial Data
```json
{context_payload}
```
"""
    response = model.invoke([
        SystemMessage(content=MEDIA_ARTICLE_SYSTEM_PROMPT),
        HumanMessage(content=article_prompt),
    ])
    return getattr(response, "content", "")


def generate_reel_script(
    article_markdown: str,
    model: Any,
    character_pair: str = "peter_stewie",
    reel_temperature: float = 0.4,
) -> tuple[list[dict[str, Any]], str, str]:
    """Generate a Faceless-compatible video reel dialogue script from the published article.

    Args:
        article_markdown: The cited article text to transform into a dialogue.
        model: LLM model instance.
        character_pair: Character duo ('peter_stewie' or 'rick_morty').
        reel_temperature: Temperature for creative dialogue generation.

    Returns:
        Tuple of (dialogue_json, reel_script_text, caption_text).
    """
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

    reel_sys_prompt = (
        MEDIA_REEL_SYSTEM_PROMPT
        .replace("{cast_name}", cast_name)
        .replace("{persona_instructions}", persona_instructions)
        .replace("{first_voice}", first_voice)
        .replace("{second_voice}", second_voice)
    )
    reel_prompt = f"""Create the 60–75 second viral dialogue reel based on this published research article:
```markdown
{article_markdown}
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

    dialogue_lines: list[dict[str, Any]] = []
    caption_text = f"The hidden financial truth. 🚨 Read the full verified audit in bio. #investing #stocks #finance"

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
        logger.warning("Dialogue JSON generation error: %s; using safe fallback", exc)
        dialogue_lines = [
            {"index": 0, "voiceId": first_voice, "text": "(confused) Wait, what did the forensic research find?"},
            {"index": 1, "voiceId": second_voice, "text": "(confident) We pulled the official SEC filings and consensus data for a full audit."},
            {"index": 2, "voiceId": first_voice, "text": "(skeptical) Are the claims verified by primary regulatory sources?"},
            {"index": 3, "voiceId": second_voice, "text": "(deadpan) Check the complete verified memo and source receipts below."},
        ]

    script_lines = []
    for line in dialogue_lines:
        spk = "Speaker A" if line.get("voiceId") == first_voice else "Speaker B"
        script_lines.append(f"[{spk}]: {line.get('text')}")
    reel_script_text = "\n\n".join(script_lines)

    return dialogue_lines, reel_script_text, caption_text


# ---------------------------------------------------------------------------
# Legacy wrapper preserved for backward compatibility with existing tests
# ---------------------------------------------------------------------------
def generate_media_package(
    state: InvestigationState,
    model: Any,
    character_pair: str = "peter_stewie",
    reel_temperature: float = 0.4,
) -> MediaPackage:
    """Generate the cited forensic article and Faceless video reel package.

    Legacy wrapper that calls the decoupled generators. New code should use
    generate_article_markdown and generate_reel_script directly.

    Args:
        state: InvestigationState with audited facts and consensus.
        model: LLM model instance.
        character_pair: 'peter_stewie' or 'rick_morty'.
        reel_temperature: Higher temperature for comedic banter generation (default 0.4).

    Returns:
        MediaPackage with article.md and dialogue.json.
    """
    ticker = state.get("ticker") or "UNKNOWN"
    evidence = state.get("evidence", [])
    if not evidence or any(not item.get("source_url") or not item.get("quote") for item in evidence):
        raise ValueError("Media generation requires cited primary evidence; uncited material claims are blocked.")

    # Build a minimal memo from state for the legacy path
    from app.agent.memo import render_forensic_memo, render_research_report
    explicit_position_request = bool((state.get("research_intent") or {}).get("requested_position_decision"))
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    final_text = getattr(last_message, "content", "") if last_message else ""
    memo_md = (
        render_forensic_memo(state, final_text)
        if explicit_position_request and state.get("ticker")
        else render_research_report(state, final_text)
    )

    article_md = generate_article_markdown(memo_md, state, model)
    dialogue_json, reel_script_text, caption_text = generate_reel_script(
        article_md, model, character_pair=character_pair, reel_temperature=reel_temperature,
    )

    return MediaPackage(
        ticker=ticker,
        article_markdown=article_md,
        dialogue_json=dialogue_json,
        reel_script_text=reel_script_text,
        caption_text=caption_text,
    )
