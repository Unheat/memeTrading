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

MEDIA_ARTICLE_SYSTEM_PROMPT = """You are a senior financial investigative journalist and former hedge fund partner.
Your mission is to write a deeply cited, publication-grade forensic research article (Substack / Institutional Investment Note style).

RULES FOR CITATIONS:
1. Every factual statement, financial metric, or consensus target MUST cite its primary source using the exact bracketed tags from the Verified Primary Source Registry (e.g. [1], [2]).
2. DO NOT invent, hallucinate, or alter any citation numbers, accession numbers, or URLs. Only cite from the provided registry tags.
3. Include clear Markdown comparison tables for:
   - SEC XBRL Margins & Financial Trajectory
   - Wall Street Consensus vs Reality (The Expectation Gap)
4. Highlight the 2 Quantitative Numeric Kill Criteria formulated by the Adversarial Red Team.
5. Conclude your analytical write-up cleanly; the verified regulatory bibliography will be attached automatically.
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
class CitationCard:
    """A verified source record pre-bound to its audited facts and quotes."""

    index: int
    tag: str  # e.g. "[1]"
    source_type: str  # "SEC Filing", "Consensus", "Market Data", "Financial News"
    title: str
    url: str
    accession: str | None = None
    filing_date: str | None = None
    facts: tuple[str, ...] = ()
    quotes: tuple[str, ...] = ()

    def format_prompt_block(self) -> str:
        """Render this card as a concise reference entry for the LLM prompt."""
        lines = [f"{self.tag} **{self.title}**"]
        details = []
        if self.accession:
            details.append(f"Accession: `{self.accession}`")
        if self.filing_date:
            details.append(f"Filing Date: {self.filing_date}")
        if self.url:
            details.append(f"URL: {self.url}")
        if details:
            lines.append(f"    {' | '.join(details)}")
        if self.facts:
            lines.append("    Audited Facts:")
            for f in self.facts:
                lines.append(f"    • {f}")
        if self.quotes:
            lines.append("    Primary Excerpts:")
            for q in self.quotes:
                lines.append(f"    • \"{q}\"")
        return "\n".join(lines)

    def format_bibliography_entry(self) -> str:
        """Render this card as an authoritative Markdown bibliography entry."""
        meta = []
        if self.accession:
            meta.append(f"SEC Accession `{self.accession}`")
        if self.filing_date:
            meta.append(f"Filing Date: {self.filing_date}")
        if self.url:
            meta.append(f"[Official Source]({self.url})")
        meta_str = " | ".join(meta) if meta else self.source_type

        entry = [f"{self.index}. **{self.title}** ({meta_str})"]
        if self.facts:
            entry.append(f"   * *Key Facts:* {'; '.join(self.facts[:5])}")
        if self.quotes:
            entry.append(f"   * *Primary Quote:* \"{self.quotes[0]}\"")
        return "\n".join(entry)


@dataclass(frozen=True)
class MediaPackage:
    """Synchronized video reel script and cited research article."""

    ticker: str
    article_markdown: str
    dialogue_json: list[dict[str, Any]]
    reel_script_text: str
    caption_text: str


def build_source_registry(state: InvestigationState) -> list[CitationCard]:
    """Compile verified sources from state into pre-indexed citation cards.

    Pairs every audited number, SEC filing, consensus target, and market quote
    to an immutable 1-based index ([1], [2], [3]...).

    Args:
        state: Completed investigation state.

    Returns:
        List of pre-indexed CitationCard objects.
    """
    cards: list[CitationCard] = []
    ticker = state.get("ticker") or "RESEARCH"
    card_idx = 1

    # 1. SEC Financials & XBRL Accounting Card
    sec_fin = state.get("sec_financials")
    if not sec_fin:
        for cand in (state.get("candidates") or {}).values():
            if isinstance(cand, Mapping) and cand.get("sec_financials"):
                sec_fin = cand["sec_financials"]
                break

    if sec_fin and isinstance(sec_fin, Mapping) and sec_fin.get("status") in {"ok", "ok_foreign_issuer_unstructured"}:
        periods = sec_fin.get("periods") or ()
        sec_facts = []
        rev_map = sec_fin.get("revenue") or {}
        gm_map = sec_fin.get("gross_margin_pct") or {}
        cfo_map = sec_fin.get("cash_from_operations") or {}
        capex_map = sec_fin.get("capex") or {}
        debt_map = sec_fin.get("total_debt") or {}
        cash_map = sec_fin.get("cash_and_equivalents") or {}

        for p in list(periods)[:3]:
            parts = []
            if p in rev_map and rev_map[p] is not None:
                parts.append(f"Revenue: ${float(rev_map[p]) / 1e9:.2f}B")
            if p in gm_map and gm_map[p] is not None:
                parts.append(f"Gross Margin: {float(gm_map[p]) * 100:.1f}%")
            if p in cfo_map and cfo_map[p] is not None:
                parts.append(f"CFO: ${float(cfo_map[p]) / 1e9:.2f}B")
            if p in capex_map and capex_map[p] is not None:
                parts.append(f"CapEx: ${float(capex_map[p]) / 1e9:.2f}B")
            if parts:
                sec_facts.append(f"Period {p}: {', '.join(parts)}")

        if sec_fin.get("ttm_fcf") is not None:
            sec_facts.append(f"TTM Free Cash Flow Base: ${float(sec_fin['ttm_fcf']) / 1e9:.2f}B")
        if periods and periods[0] in debt_map and debt_map[periods[0]] is not None:
            sec_facts.append(f"Latest Total Debt: ${float(debt_map[periods[0]]) / 1e9:.2f}B")
        if periods and periods[0] in cash_map and cash_map[periods[0]] is not None:
            sec_facts.append(f"Latest Cash & Equivalents: ${float(cash_map[periods[0]]) / 1e9:.2f}B")

        sec_url = f"https://www.sec.gov/edgar/browse/?CIK={ticker}"
        cards.append(
            CitationCard(
                index=card_idx,
                tag=f"[{card_idx}]",
                source_type="SEC Filing",
                title=f"U.S. Securities & Exchange Commission (SEC) — Official XBRL Financial Statements (${ticker})",
                url=sec_url,
                accession=str(sec_fin.get("provider", "SEC-EDGAR-XBRL")),
                facts=tuple(sec_facts),
            )
        )
        card_idx += 1

    # 2. Wall Street Consensus & Analyst Expectations Card
    consensus = state.get("consensus_snapshot")
    if not consensus:
        for cand in (state.get("candidates") or {}).values():
            if isinstance(cand, Mapping) and cand.get("consensus_snapshot"):
                consensus = cand["consensus_snapshot"]
                break

    if consensus and isinstance(consensus, Mapping):
        con_facts = []
        ratings = consensus.get("ratings") or {}
        tot_ratings = sum(int(v) for v in ratings.values() if isinstance(v, (int, float)))
        if tot_ratings > 0:
            rating_detail = ", ".join(f"{k.replace('_', ' ').title()}: {v}" for k, v in ratings.items() if v)
            con_facts.append(f"Analyst Ratings: {tot_ratings} covering analysts ({rating_detail})")

        pt_mean = consensus.get("target_mean_price")
        pt_low = consensus.get("target_low_price")
        pt_high = consensus.get("target_high_price")
        if pt_mean is not None:
            con_facts.append(f"Price Target Spectrum: Mean ${pt_mean:.2f}, Low ${pt_low or 0:.2f}, High ${pt_high or 0:.2f}")

        rev_est = consensus.get("revenue_estimates")
        if isinstance(rev_est, list):
            for r_item in rev_est:
                if isinstance(r_item, Mapping):
                    p_name = r_item.get("period")
                    avg_val = r_item.get("avg")
                    if avg_val is not None:
                        con_facts.append(f"Consensus Revenue ({p_name}): ${float(avg_val) / 1e9:.2f}B")
        elif isinstance(rev_est, Mapping):
            if rev_est.get("current_year_avg"):
                con_facts.append(f"Consensus FY0 Revenue: ${float(rev_est['current_year_avg']) / 1e9:.2f}B")
            if rev_est.get("next_year_avg"):
                con_facts.append(f"Consensus FY1 (+1Y) Revenue: ${float(rev_est['next_year_avg']) / 1e9:.2f}B")

        eps_est = consensus.get("eps_estimates")
        if isinstance(eps_est, list):
            for e_item in eps_est:
                if isinstance(e_item, Mapping):
                    p_name = e_item.get("period")
                    avg_val = e_item.get("avg")
                    if avg_val is not None:
                        con_facts.append(f"Consensus EPS ({p_name}): ${float(avg_val):.2f}")
        elif isinstance(eps_est, Mapping):
            if eps_est.get("current_year_avg"):
                con_facts.append(f"Consensus FY0 EPS: ${float(eps_est['current_year_avg']):.2f}")
            if eps_est.get("next_year_avg"):
                con_facts.append(f"Consensus FY1 (+1Y) EPS: ${float(eps_est['next_year_avg']):.2f}")

        cards.append(
            CitationCard(
                index=card_idx,
                tag=f"[{card_idx}]",
                source_type="Consensus",
                title=f"Wall Street Consensus Aggregator & Broker Estimates Archive (${ticker})",
                url=f"https://finance.yahoo.com/quote/{ticker}",
                facts=tuple(con_facts),
            )
        )
        card_idx += 1

    # 3. Real-Time Market Quotation & Execution Analytics Card
    market = state.get("market_context")
    if not market:
        for cand in (state.get("candidates") or {}).values():
            if isinstance(cand, Mapping) and cand.get("market_context"):
                market = cand["market_context"]
                break

    if market and isinstance(market, Mapping) and market.get("quote"):
        q = market.get("quote") or {}
        m_facts = []
        if q.get("price") is not None:
            m_facts.append(f"Latest Market Price: ${float(q['price']):.2f}")
        if q.get("market_cap") is not None:
            m_facts.append(f"Market Capitalization: ${float(q['market_cap']) / 1e9:.2f}B")
        vol_ratio = market.get("volume_ratio_20d", {}).get("value")
        if vol_ratio is not None:
            m_facts.append(f"20-Day Volume Ratio: {vol_ratio:.2f}x")
        ret_1m = market.get("returns", {}).get("1m", {}).get("value")
        if ret_1m is not None:
            m_facts.append(f"1-Month Total Return: {ret_1m * 100:+.1f}%")
        ret_3m = market.get("returns", {}).get("3m", {}).get("value")
        if ret_3m is not None:
            m_facts.append(f"3-Month Total Return: {ret_3m * 100:+.1f}%")

        cards.append(
            CitationCard(
                index=card_idx,
                tag=f"[{card_idx}]",
                source_type="Market Data",
                title=f"Market Quotation & Execution Analytics (${ticker})",
                url=f"https://finance.yahoo.com/quote/{ticker}",
                filing_date=str(q.get("as_of", ""))[:10] or None,
                facts=tuple(m_facts),
            )
        )
        card_idx += 1

    # 4. Primary SEC Filing Claims & Excerpt Citations
    seen_urls: set[str] = set()
    evidence_items: list[dict[str, Any]] = []

    for ev in state.get("evidence", []):
        if isinstance(ev, Mapping) and ev.get("source_url"):
            evidence_items.append(dict(ev))

    for cand in (state.get("candidates") or {}).values():
        if isinstance(cand, Mapping):
            for ev in cand.get("evidence", []):
                if isinstance(ev, Mapping) and ev.get("source_url"):
                    evidence_items.append(dict(ev))

    for item in evidence_items:
        url = str(item.get("source_url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        form = item.get("form") or "SEC Filing"
        accession = item.get("accession")
        f_date = str(item.get("filing_date") or "") or None
        quote = str(item.get("quote") or "").strip()
        title = f"SEC Form {form} Document Excerpt" if accession else (item.get("title") or "Primary Source Reference")

        cards.append(
            CitationCard(
                index=card_idx,
                tag=f"[{card_idx}]",
                source_type="SEC Filing" if accession else "Primary Article",
                title=title,
                url=url,
                accession=accession,
                filing_date=f_date,
                quotes=(quote[:300],) if quote else (),
            )
        )
        card_idx += 1

    return cards


def format_source_registry_for_prompt(cards: list[CitationCard]) -> str:
    """Format citation cards into a clean Markdown block for LLM prompt context."""
    if not cards:
        return "No pre-indexed primary sources available."
    return "\n\n".join(card.format_prompt_block() for card in cards)


def format_bibliography_markdown(cards: list[CitationCard]) -> str:
    """Format citation cards into a deterministic bibliography section."""
    if not cards:
        return ""
    lines = ["## Primary Sources & Regulatory Receipts\n"]
    for card in cards:
        lines.append(card.format_bibliography_entry() + "\n")
    return "\n".join(lines).strip()


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
    """Generate a publication-grade cited Substack article with pre-indexed citation cards.

    The article writer receives:
    1. The fully rendered memo_markdown (ground truth analysis).
    2. The pre-indexed Citation Cards ([1], [2], [3]...) explicitly binding each source to its facts.
    Python then attaches the deterministic bibliography at the bottom.

    Args:
        memo_markdown: The finalized forensic research memo text.
        state: Completed investigation state for extracting evidence receipts.
        model: LLM model instance.

    Returns:
        Article markdown string with verified citations and regulatory receipts.
    """
    ticker = state.get("ticker") or "RESEARCH"
    company = state.get("company") or ""
    cards = build_source_registry(state)
    registry_text = format_source_registry_for_prompt(cards)

    article_prompt = f"""Write an institutional, deeply cited forensic research article for ${ticker} ({company}).

## Verified Primary Source Registry (Cite using the exact tags like [1], [2] next to claims)
{registry_text}

## Audited Research Memo (Ground Truth — cite only from this content)
```markdown
{memo_markdown}
```
"""
    response = model.invoke([
        SystemMessage(content=MEDIA_ARTICLE_SYSTEM_PROMPT),
        HumanMessage(content=article_prompt),
    ])
    article_raw = getattr(response, "content", "")

    # Strip any model-generated trailing bibliography to avoid duplicates or hallucinated links
    clean_article = re.split(
        r"\n##\s*(?:Primary Sources|Regulatory Receipts|References|Sources)",
        article_raw,
        flags=re.IGNORECASE,
    )[0].strip()

    # Deterministically append the authoritative bibliography from the verified Python cards
    bibliography = format_bibliography_markdown(cards)
    if bibliography:
        return f"{clean_article}\n\n---\n\n{bibliography}\n"
    return clean_article


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

    Legacy wrapper that calls the decoupled generators.

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
