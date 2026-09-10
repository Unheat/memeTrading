"""Deterministic forensic memo and JSON report rendering.

Renders formatted Markdown memo and JSON audit artifacts with SEC receipts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from app.agent.state import InvestigationState


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
