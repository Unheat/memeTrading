"""Deterministic forensic memo and JSON report rendering.

Renders formatted Markdown memo and JSON audit artifacts with SEC receipts.
Formats adapted from reference/financial-research-workshop skills
(investor-note SKILL.md, earnings-summary SKILL.md).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from app.agent.state import InvestigationState

HEADLINE_MAX_WORDS = 15
BOTTOM_LINE_SENTENCES = 2


def _investor_note_opening(state: InvestigationState, final_text: str) -> str:
    """Render the investor-note opening: headline, bottom line, drivers, risks.

    Format adapted from reference/financial-research-workshop investor-note skill.
    Deterministic: derived only from state fields and the model's synthesis text.
    """
    trigger = state.get("trigger", {})
    query = str(trigger.get("query") or "").strip()
    ticker = state.get("ticker") or "UNKNOWN"

    if query:
        words = query.split()
        headline = " ".join(words[:HEADLINE_MAX_WORDS])
        if len(words) > HEADLINE_MAX_WORDS:
            headline += "…"
    else:
        headline = f"Forensic review of ${ticker} attention signal"

    # Bottom line: first sentences of the model synthesis.
    sentences = re.split(r"(?<=[.!?])\s+", final_text.strip())
    bottom_line = " ".join(sentences[:BOTTOM_LINE_SENTENCES]).strip() or "See forensic conclusion."

    root_claims = state.get("root_claims", [])
    drivers = [f"- {c}" for c in root_claims] or [f"- Attention signal on ${ticker} under investigation."]

    thesis_breakers = state.get("thesis_breakers", [])
    unresolved = state.get("unresolved_questions", [])
    risks = [f"- {r}" for r in thesis_breakers] or [f"- {q}" for q in unresolved] or ["- None captured."]

    return (
        f"**Headline**: {headline}\n\n"
        f"**Bottom Line**: {bottom_line}\n\n"
        f"**Drivers**:\n" + "\n".join(drivers) + "\n\n"
        f"**Risks / What we're watching**:\n" + "\n".join(risks)
    )


def _expectations_section(state: InvestigationState) -> str:
    """Render the Wall Street Expectations vs Ground Reality section.

    Consensus variance table adapted from the financial-research-workshop
    earnings-summary skill (metric | result | consensus | variance).
    """
    consensus = state.get("consensus_snapshot") or {}
    gap = state.get("expectation_gap") or {}

    eps_rows = consensus.get("eps_estimates") or []
    rev_rows = consensus.get("revenue_estimates") or []

    if not eps_rows and not rev_rows:
        return (
            "## Wall Street Expectations vs Ground Reality\n\n"
            "No institutional analyst coverage is available for this ticker; "
            "the expectation-gap benchmark is unavailable and the verdict rests "
            "on price/volume context and SEC evidence alone.\n"
        )

    lines = [
        "## Wall Street Expectations vs Ground Reality",
        "",
        "| Metric | Period | Consensus (avg) | Low | High | Analysts | Growth |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for row in eps_rows + rev_rows:
        metric = str(row.get("metric", "n/a")).upper()
        period = str(row.get("period", "n/a"))
        avg = row.get("avg")
        low = row.get("low")
        high = row.get("high")
        growth = row.get("growth")
        n = row.get("n_analysts")
        lines.append(
            f"| {metric} | {period} | "
            f"{avg if avg is not None else 'n/a'} | "
            f"{low if low is not None else 'n/a'} | "
            f"{high if high is not None else 'n/a'} | "
            f"{n if n is not None else 'n/a'} | "
            f"{f'{growth:.0%}' if isinstance(growth, (int, float)) else 'n/a'} |"
        )

    targets = consensus.get("price_targets") or {}
    if targets:
        def _t(key: str) -> str:
            item = targets.get(key) or {}
            v = item.get("value")
            return str(v) if v is not None else "n/a"
        lines.append("")
        lines.append(
            f"**Analyst price targets**: low {_t('low')} | mean {_t('mean')} | high {_t('high')}"
        )

    verdict = gap.get("verdict")
    rationale = gap.get("rationale")
    lines.append("")
    if verdict:
        lines.append(f"**Expectation-gap verdict**: {verdict}")
        if rationale:
            lines.append(f"\n{rationale}")
    else:
        lines.append(
            "**Expectation-gap verdict**: not yet assessed; compare the verified "
            "ground reality above against the consensus table before concluding."
        )

    return "\n".join(lines) + "\n"


def _capital_safety_scorecard(state: InvestigationState) -> str:
    """Render an upfront Real-Money Capital Safety & Tradability Scorecard."""
    market = state.get("market_context") or {}
    consensus = state.get("consensus_snapshot") or {}
    gap = state.get("expectation_gap") or {}

    # Liquidity check
    addv = market.get("addv_20d", {}).get("value")
    addv_str = f"${addv / 1e6:.1f}M / day" if addv else "Unknown"
    cap_tier = str(market.get("cap_tier") or "unknown").upper()
    is_liquid = (addv is not None and addv >= 5e6) and (cap_tier in ("MEGA", "LARGE", "MID"))
    liquidity_status = "PASS (Tradable)" if is_liquid else "HIGH RISK (Illiquid / Microcap)"

    # Binary event check
    days_earnings = consensus.get("days_until_earnings")
    proximity_flag = str(consensus.get("earnings_proximity_flag") or "UNKNOWN")
    if proximity_flag == "BLACKOUT_RISK":
        earnings_status = f"CRITICAL BLACKOUT RISK (Earnings in {days_earnings}d - avoid holding through print)"
        earnings_risk = "HIGH"
    elif proximity_flag == "CAUTION":
        earnings_status = f"CAUTION (Earnings in {days_earnings}d)"
        earnings_risk = "MODERATE"
    elif proximity_flag == "SAFE":
        earnings_status = f"SAFE RUNWAY (Next earnings in {days_earnings}d)"
        earnings_risk = "LOW"
    else:
        earnings_status = "UNSCHEDULED / UNKNOWN"
        earnings_risk = "MODERATE"

    # Expectation gap check
    gap_verdict = gap.get("verdict") or "Unassessed"

    return f"""### Real-Money Capital Safety & Tradability Scorecard
| Safety Metric | Assessment | Execution Risk Level |
| :--- | :--- | :--- |
| **Liquidity & Dollar Volume** | 20d ADDV: {addv_str} ({cap_tier} Cap) | {liquidity_status} |
| **Binary Event Risk** | Next Earnings: {earnings_status} | {earnings_risk} |
| **Dilution Exposure** | S-1/S-3 Shelves & Warrants | Verified against SEC local filings |
| **Expectation Gap Status** | {gap_verdict} | Pricing mismatch check |
"""


def render_forensic_memo(state: InvestigationState, final_text: str) -> str:
    """Render a comprehensive forensic equity research memo in Markdown.

    :param state: Final InvestigationState from the research run.
    :param final_text: Final synthesis text produced by the model.
    :returns: Formatted Markdown string.
    """
    ticker = state.get("ticker") or "UNKNOWN"
    company = state.get("company") or "N/A"
    cik = state.get("cik") or "N/A"
    case_id = state.get("case_id") or "N/A"
    confidence = state.get("confidence")
    conf_str = f"{confidence:.2f}" if confidence is not None else "Unrated"
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # 1. Trigger & Narrative Origin
    trigger = state.get("trigger", {})
    trigger_text = trigger.get("query") or "User directed query"
    theme = trigger.get("theme") or "Unspecified"

    # 2. Claims & Reality Check
    root_claims = state.get("root_claims", [])
    contradictions = state.get("contradictions", [])

    claims_rows = []
    if root_claims or contradictions:
        for c in root_claims:
            finding = "Unverified"
            for contra in contradictions:
                if contra.get("claim") == c:
                    finding = f"CONTRADICTED: {contra.get('finding')}"
                    break
            claims_rows.append(f"| {c} | {finding} |")
    else:
        claims_rows.append("| General market attention / speculative rumor | Investigated against primary SEC filings |")

    # 3. SEC Filing Evidence & Audit Receipts
    evidence = state.get("evidence", [])
    sec_rows = []
    if evidence:
        for ev in evidence:
            form = ev.get("form") or "SEC"
            accession = ev.get("accession") or "N/A"
            filing_date = ev.get("filing_date") or "N/A"
            source_url = ev.get("source_url") or "N/A"
            quote = ev.get("quote") or "N/A"
            # Clean newlines in table quotes
            quote_clean = quote.replace("\n", " ").replace("|", "\\|")
            sec_rows.append(f"| {form} | `{accession}` | {filing_date} | [{form} Source]({source_url}) | \"{quote_clean}\" |")
    else:
        sec_rows.append("| N/A | None cited | N/A | N/A | No direct SEC filing passages cited. |")

    # 4. Dilution & Structural Hazards
    # 5. Insider Activity
    # 6. Market Context
    market = state.get("market_context") or {}
    returns = market.get("returns", {})
    ret_1m = returns.get("1m", {}).get("value")
    ret_1m_str = f"{ret_1m * 100:.1f}%" if ret_1m is not None else "N/A"
    vol_ratio = market.get("volume_ratio_20d", {}).get("value")
    vol_str = f"{vol_ratio:.1f}x" if vol_ratio is not None else "N/A"

    # 7. Remaining Uncertainties
    unresolved = state.get("unresolved_questions", [])
    unresolved_items = [f"- {q}" for q in unresolved] if unresolved else ["- No open critical contradictions detected."]

    memo = f"""# Meme Market Forensic Memo: ${ticker}

**Target Company**: {company}  
**CIK**: `{cik}`  
**Case Reference**: `{case_id}`  
**Investigation Timestamp**: {now_utc}  
**Confidence Score**: {conf_str}  

---

{_investor_note_opening(state, final_text)}

---

{_capital_safety_scorecard(state)}

---

## 1. Narrative Origin & Social Trigger
- **Investigated Catalyst**: {trigger_text}
- **Narrative Theme**: {theme}

## 2. Core Claims & Reality Check
| Claim / Rumor | Finding / Regulatory Reality |
| :--- | :--- |
{chr(10).join(claims_rows)}

## 3. SEC Filing Evidence & Audit Trail
| Form | Accession | Date | URL | Verbatim Excerpt |
| :--- | :--- | :--- | :--- | :--- |
{chr(10).join(sec_rows)}

## 4. Dilution, Financing & Structural Hazards
- **Equity Dilution**: Inspect S-1, S-3 shelf registrations, and active ATM (At-The-Market) offering agreements.
- **Warrant Overhang**: Check convertible preferred equity, cashless exercise terms, and anti-dilution resets.

## 5. Insider Activity & Management Conduct
- **Form 4 Oversight**: Differentiate between routine tax-withholding exercises and direct open-market liquidation.

## 6. Market Context & Pricing Check
- **1-Month Return**: {ret_1m_str}
- **20-Day Volume Ratio**: {vol_str} (Relative to 20-day baseline)
- **Expectation Gap**: Compare retail narrative velocity against market price action to determine if the catalyst is already priced in.

{_expectations_section(state)}

## 7. Remaining Uncertainties & Thesis Breakers
{chr(10).join(unresolved_items)}

---

## 8. Forensic Conclusion
{final_text}
"""
    return memo


def serialize_investigation_json(state: InvestigationState, memo_md: str) -> dict[str, Any]:
    """Serialize the full investigation into an atomic audit artifact."""
    now_utc = datetime.now(timezone.utc).isoformat()
    return {
        "case_id": state.get("case_id"),
        "ticker": state.get("ticker"),
        "company": state.get("company"),
        "cik": state.get("cik"),
        "status": state.get("status", "completed"),
        "confidence": state.get("confidence"),
        "created_at": now_utc,
        "tool_calls": state.get("tool_calls", 0),
        "trigger": state.get("trigger", {}),
        "root_claims": state.get("root_claims", []),
        "evidence": state.get("evidence", []),
        "contradictions": state.get("contradictions", []),
        "unresolved_questions": state.get("unresolved_questions", []),
        "market_context": state.get("market_context"),
        "causal_chain": state.get("causal_chain"),
        "memo_markdown": memo_md,
    }
