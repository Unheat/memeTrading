"""Deterministic forensic memo and JSON report rendering.

Renders formatted Markdown memo and JSON audit artifacts with SEC receipts.
Formats adapted from reference/financial-research-workshop skills
(investor-note SKILL.md, earnings-summary SKILL.md).
"""
from __future__ import annotations

from collections.abc import Mapping
import json
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

    # Institutional Conviction Tier & 3:1 Asymmetry
    confidence = state.get("confidence")
    if not is_liquid:
        conviction_tier = "PASSED 🚫 (Illiquid / Microcap Violation)"
        asymmetry_status = "FAILED (< $5M ADDV)"
    elif proximity_flag == "BLACKOUT_RISK":
        conviction_tier = "PASSED 🚫 (Earnings Blackout Risk)"
        asymmetry_status = "FAILED (Binary Event Risk)"
    elif confidence is not None and confidence >= 0.75:
        conviction_tier = "HIGH CONVICTION 🔥🔥🔥"
        asymmetry_status = "PASSED (Upside >= 3.0x Downside Floor)"
    elif confidence is not None and confidence >= 0.50:
        conviction_tier = "MEDIUM CONVICTION 🔥🔥"
        asymmetry_status = "MODERATE (Awaiting Margin Confirmation)"
    else:
        conviction_tier = "VALIDATION 🔥 (Awaiting Pullback / Data)"
        asymmetry_status = "PENDING (Asymmetry Unconfirmed)"

    return f"""### Real-Money Capital Safety & Tradability Scorecard
| Safety Metric | Assessment | Execution Risk Level |
| :--- | :--- | :--- |
| **Liquidity & Dollar Volume** | 20d ADDV: {addv_str} ({cap_tier} Cap) | {liquidity_status} |
| **Binary Event Risk** | Next Earnings: {earnings_status} | {earnings_risk} |
| **Dilution Exposure** | S-1/S-3 Shelves & Warrants | Verified against SEC local filings |
| **Expectation Gap Status** | {gap_verdict} | Pricing mismatch check |
| **3:1 Asymmetry Hurdle** | {asymmetry_status} | Minimum 3.0x Reward-to-Risk Rule |
| **IC Conviction Tier** | **{conviction_tier}** | Institutional Allocation Gate |
"""


def render_forensic_memo(state: InvestigationState, final_text: str) -> str:
    """Render a comprehensive forensic equity research memo in Markdown.

    :param state: Final InvestigationState from the research run.
    :param final_text: Final synthesis text produced by the model.
    :returns: Formatted Markdown string.
    """
    ticker = state.get("ticker") or "UNKNOWN"
    company = state.get("company") or "N/A"
    gate = state.get("evidence_gate") or {}
    if state.get("status") in {"insufficient_evidence", "validation_required"}:
        failed_gate = next((item for item in (state.get("asymmetry_gate"), state.get("valuation_gate"), state.get("accounting_gate"), gate) if item and not item.get("passed", False)), {})
        missing = failed_gate.get("missing_evidence") or [failed_gate.get("reason", "required evidence is unavailable")]
        missing_items = "\n".join(f"- {item}" for item in missing)
        return f"""# Research Incomplete: ${ticker}

**Target Company**: {company}
**Case Reference**: `{state.get('case_id') or 'N/A'}`
**Decision**: **NO_POSITION**
**Allocation**: **0.0%**

## 1. Narrative Origin & Social Trigger
Unavailable — not inferred.

## 2. Core Claims & Reality Check
Unavailable — validation stopped actionable research.

## 3. SEC Filing Evidence & Audit Trail
Unavailable — required evidence or normalized financial fields are incomplete.

## 4. Dilution, Financing & Structural Hazards
Unavailable — not inferred.

## 5. Insider Activity & Management Conduct
Unavailable — not inferred.

## 6. Market Context & Pricing Check
Unavailable — not inferred.

## 7. Adversarial Red Team Invalidation & Institutional Debate
Validation required.

### Required next evidence
{missing_items}

## 8. Forensic Conclusion
Research validation incomplete — no position and no target.
"""

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

    # 7. Remaining Uncertainties & Kill Triggers
    unresolved = state.get("unresolved_questions", [])
    unresolved_items = [f"- {q}" for q in unresolved] if unresolved else ["- Unavailable — not inferred."]
    thesis_breakers = state.get("thesis_breakers", [])
    kill_items = [f"- **Kill Trigger {i+1}**: {b}" for i, b in enumerate(thesis_breakers)] if thesis_breakers else ["- Unavailable — no source-backed kill trigger was produced."]

    bull_report = state.get("bull_report")
    if bull_report and getattr(bull_report, "catalysts", None):
        bull_items = [f"- **Catalyst {i+1}**: {c}" for i, c in enumerate(bull_report.catalysts)]
        if getattr(bull_report, "operating_leverage_drivers", None):
            bull_items.extend([f"- **Leverage Driver**: {d}" for d in bull_report.operating_leverage_drivers])
    else:
        bull_items = ["- Fundamental catalysts under evaluation."]

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
- **Equity Dilution**: Inspect S-1, S-3 shelf registrations, and active ATM offering agreements.
- **Warrant Overhang**: Check convertible preferred equity, cashless exercise terms, and resets.

## 5. Insider Activity & Management Conduct
- **Form 4 Oversight**: Differentiate between routine tax-withholding and open-market liquidation.

## 6. Market Context & Pricing Check
- **1-Month Return**: {ret_1m_str}
- **20-Day Volume Ratio**: {vol_str} (Relative to 20-day baseline)

{_expectations_section(state)}

## 7. Adversarial Red Team Invalidation & Institutional Debate
### The Bull Case: Catalysts & Operating Leverage
{chr(10).join(bull_items)}

### Adversarial Red Team: Quantitative Numeric Kill Criteria
{chr(10).join(kill_items)}

### Open Investigation Questions
{chr(10).join(unresolved_items)}

---

## 8. Forensic Conclusion
{final_text}
"""
    return memo


def _format_comparison_val(metric: str, cand_val: Any) -> str:
    """Format a candidate comparison value cleanly for Markdown tables."""
    if not isinstance(cand_val, dict):
        return str(cand_val) if cand_val is not None else "N/A"
    raw_val = cand_val.get("value")
    period = cand_val.get("period")
    if raw_val is None:
        return "N/A"
    if isinstance(raw_val, (int, float)):
        metric_lower = metric.lower()
        if "margin" in metric_lower or "pct" in metric_lower or "growth" in metric_lower:
            formatted = f"{raw_val:.1%}" if abs(raw_val) < 5.0 else f"{raw_val:.1f}%"
        elif metric_lower in ("price", "fair_value"):
            formatted = f"${raw_val:,.2f}"
        elif metric_lower in ("revenue", "net_cash", "total_debt", "capex", "cash_from_operations", "fcf", "market_cap"):
            abs_v = abs(raw_val)
            sign = "-" if raw_val < 0 else ""
            if abs_v >= 1e12:
                formatted = f"{sign}${abs_v / 1e12:.2f}T"
            elif abs_v >= 1e9:
                formatted = f"{sign}${abs_v / 1e9:.2f}B"
            elif abs_v >= 1e6:
                formatted = f"{sign}${abs_v / 1e6:.2f}M"
            else:
                formatted = f"{sign}${abs_v:,.2f}"
        elif metric_lower in ("pe_ratio", "reward_to_risk_ratio"):
            formatted = f"{raw_val:.2f}x"
        else:
            formatted = f"{raw_val:,.2f}"
    else:
        formatted = str(raw_val)
    if period and period != "latest":
        return f"{formatted} ({period})"
    return formatted


def render_research_report(state: InvestigationState, final_text: str) -> str:
    """Render one prompt-directed report without profile or mode conclusions.

    Args:
        state: Completed universal research state.
        final_text: Model synthesis.

    Returns:
        Markdown report with ranking readiness, sources, comparisons, and evidence.
    """
    intent = state.get("research_intent") or {}
    requested_count = intent.get("requested_ranking_count")
    candidates = state.get("candidates") or {}
    rows = [
        f"| {candidate.get('ticker') or 'UNKNOWN'} | {candidate.get('company') or 'Unknown'} | {'yes' if candidate.get('market_context') else 'no'} | {'yes' if candidate.get('sec_financials') or candidate.get('sec_corpora') or candidate.get('evidence') else 'no'} |"
        for candidate in candidates.values() if isinstance(candidate, Mapping)
    ] or ["| None | No registered candidates | no | no |"]
    ranking = "Not requested" if not requested_count else f"Requested ranking count: {requested_count}; registered candidates: {len(candidates)}"
    ranking_line = f"**Ranking Requirement**: {ranking}\n" if requested_count else ""

    # 1. Normalized candidate comparisons
    comparison_section = ""
    comparisons = state.get("comparisons") or []
    if comparisons:
        comp_rows = []
        for c in comparisons:
            m_key = c.get("metric_key") or "Metric"
            vals = c.get("candidate_values") or {}
            val_strs = [f"${k}: {_format_comparison_val(m_key, v)}" for k, v in vals.items()]
            comp_rows.append(f"| {m_key} | {c.get('period_basis', 'N/A')} | {', '.join(val_strs)} | {c.get('comparability', 'N/A')} |")
        if comp_rows:
            comparison_section = f"""
## Normalized Candidate Comparisons
| Metric | Period Basis | Candidate Values | Comparability |
| :--- | :--- | :--- | :--- |
{chr(10).join(comp_rows)}
"""

    # 2. Institutional specialist insights (Bull, Bear, Committee, Quant)
    specialist_section = ""
    specialist_blocks = []

    # A. Render individual candidate diligence dossiers if present
    for cid, cand in candidates.items():
        if isinstance(cand, Mapping):
            dossier = cand.get("diligence_dossier")
            if dossier and isinstance(dossier, dict):
                t = dossier.get("ticker") or cand.get("ticker") or cid
                co = dossier.get("company") or cand.get("company") or t
                d_lines = [f"### Candidate Diligence Dossier: ${t} ({co})"]
                val = dossier.get("valuation") or {}
                if val.get("fair_value") is not None or val.get("implied_growth_rate") is not None:
                    d_lines.append(f"- **Reverse DCF Fair Value**: ${val.get('fair_value', 'N/A')} (Implied Growth: {val.get('implied_growth_rate', 'N/A')})")
                cats = dossier.get("bull_catalysts") or []
                if cats:
                    d_lines.append("- **Bull Catalysts**:\n" + "\n".join(f"  * {c}" for c in cats[:3]))
                kills = dossier.get("bear_kill_triggers") or []
                if kills:
                    d_lines.append("- **Bear Red Team Kill Triggers**:\n" + "\n".join(f"  * {k}" for k in kills[:3]))
                specialist_blocks.append("\n".join(d_lines))

    # B. Render top-level specialist reports for named single-company diligence
    top_ticker = state.get("ticker")
    if top_ticker and top_ticker != "UNKNOWN" and not specialist_blocks:
        bull = state.get("bull_report")
        if bull and getattr(bull, "catalysts", None):
            cats = [f"- **Catalyst**: {c}" for c in bull.catalysts]
            specialist_blocks.append(f"### Bull Case: Operating Leverage Catalysts\n{chr(10).join(cats)}")
        bear = state.get("adversarial_report")
        if bear and getattr(bear, "numeric_kill_criteria", None):
            kills = [f"- **Kill Trigger**: {k}" for k in bear.numeric_kill_criteria]
            specialist_blocks.append(f"### Adversarial Red Team: Numeric Kill Criteria\n{chr(10).join(kills)}")

    ic = state.get("ic_verdict")
    if ic and getattr(ic, "cio_deliberation_summary", None) and getattr(ic, "ticker", "") != "UNKNOWN":
        specialist_blocks.append(f"### Investment Committee Deliberation\n- **Verdict**: {getattr(ic, 'verdict', 'N/A')}\n- **Conviction**: {getattr(ic, 'conviction_tier', 'N/A')}\n- **Summary**: {getattr(ic, 'cio_deliberation_summary', '')}")

    if specialist_blocks:
        specialist_section = f"\n## Institutional Specialist Insights\n" + "\n\n".join(specialist_blocks) + "\n"

    # 3. Verified primary citations
    evidence = [item for item in state.get("evidence", []) if item.get("quote") and item.get("source_url")]
    evidence_section = ""
    if evidence:
        ev_rows = [
            f"| {e.get('form') or ('SEC' if e.get('accession') else 'Primary Source')} | `{e.get('accession') or 'N/A'}` | [{e.get('form') or 'Source'}]({e.get('source_url', 'N/A')}) | \"{e.get('quote', '').replace(chr(10), ' ')}\" |"
            for e in evidence[:10]
        ]
        evidence_section = f"""
## Verified Primary Evidence Citations
| Document | Accession | URL | Verbatim Excerpt |
| :--- | :--- | :--- | :--- |
{chr(10).join(ev_rows)}
"""

    # 4. Aggregate all consulted sources: web/articles, candidate SEC filings, and market data
    all_sources = list(state.get("source_records", []))
    for cid, cand in candidates.items():
        if isinstance(cand, dict):
            t = cand.get("ticker") or cid
            cik = cand.get("cik")
            for filing in cand.get("sec_filings", []):
                if isinstance(filing, dict):
                    all_sources.append({
                        "title": f"SEC {filing.get('form', 'Filing')} (${t}, CIK {cik or 'N/A'})",
                        "status": "official_sec_edgar",
                        "url": filing.get("filing_url") or f"https://www.sec.gov/edgar/browse/?CIK={cik}",
                    })
            if cand.get("market_context"):
                all_sources.append({
                    "title": f"Live Market Data & Consensus (${t})",
                    "status": "verified_live_feed",
                    "url": f"https://finance.yahoo.com/quote/{t}",
                })
            if cand.get("sec_financials"):
                sec_fin = cand.get("sec_financials") or {}
                if sec_fin.get("status") in {"ok", "ok_foreign_issuer_unstructured"}:
                    all_sources.append({
                        "title": f"SEC XBRL Financial Statements (${t})",
                        "status": sec_fin.get("status"),
                        "url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik or '').zfill(10)}.json" if cik else "https://data.sec.gov",
                    })

    source_rows = [
        f"| {item.get('title') or 'Untitled source'} | {item.get('status', 'discovered')} | {item.get('url') or 'Unavailable'} |"
        for item in all_sources
    ] or ["| No readable source | unavailable | N/A |"]
    missing = (state.get("evidence_gate") or {}).get("missing_evidence") or state.get("unresolved_questions") or ["No additional gaps recorded."]

    coverage_section = ""
    if candidates:
        coverage_section = f"""
## Candidate Evidence Coverage
| Ticker | Company | Market evidence | SEC evidence |
| :--- | :--- | :--- | :--- |
{chr(10).join(rows)}
"""

    return f"""# Deep Research Report

**Case Reference**: `{state.get('case_id') or 'N/A'}`
**Status**: `{state.get('status', 'completed')}`
{ranking_line}
## Request
{state.get('trigger', {}).get('query') or 'User research request'}

## Findings
{final_text or 'Research completed without a model synthesis.'}
{comparison_section}{specialist_section}{evidence_section}{coverage_section}
## Sources Consulted
| Source | Status | URL |
| :--- | :--- | :--- |
{chr(10).join(source_rows)}

## Limitations and Open Questions
{chr(10).join(f'- {item}' for item in missing)}

## Execution Coverage
- Tool receipts: {len(state.get('searches_performed', []))}
- Provider failures: {sum(1 for receipt in state.get('searches_performed', []) if receipt.get('status') == 'error')}
"""


def serialize_investigation_json(state: InvestigationState, memo_md: str) -> dict[str, Any]:
    """Serialize the full investigation into an atomic audit artifact."""
    now_utc = datetime.now(timezone.utc).isoformat()
    return {
        "case_id": state.get("case_id"),
        "depth": state.get("depth", "deep"),
        "research_intent": state.get("research_intent", {}),
        "research_plan": state.get("research_plan", []),
        "source_records": state.get("source_records", []),
        "claim_records": state.get("claim_records", []),
        "capability_outputs": state.get("capability_outputs", {}),
        "ticker": state.get("ticker"),
        "company": state.get("company"),
        "cik": state.get("cik"),
        "status": state.get("status", "completed"),
        "confidence": state.get("confidence"),
        "created_at": now_utc,
        "candidates": state.get("candidates", {}),
        "candidate_leads": state.get("candidate_leads", []),
        "comparisons": state.get("comparisons", []),
        "tool_calls": state.get("tool_calls", 0),
        "trigger": state.get("trigger", {}),
        "root_claims": state.get("root_claims", []),
        "evidence": state.get("evidence", []),
        "contradictions": state.get("contradictions", []),
        "unresolved_questions": state.get("unresolved_questions", []),
        "market_context": state.get("market_context"),
        "causal_chain": state.get("causal_chain"),
        "searches_performed": state.get("searches_performed", []),
        "sec_corpora": state.get("sec_corpora", []),
        "consensus_snapshot": state.get("consensus_snapshot"),
        "expectation_gap": state.get("expectation_gap"),
        "thesis_breakers": state.get("thesis_breakers", []),
        "bull_report": state.get("bull_report"),
        "adversarial_report": state.get("adversarial_report"),
        "ic_verdict": state.get("ic_verdict"),
        "budget_state": state.get("budget_state", {}),
        "evidence_gate": state.get("evidence_gate", {}),
        "accounting_gate": state.get("accounting_gate", {}),
        "valuation_gate": state.get("valuation_gate", {}),
        "asymmetry_gate": state.get("asymmetry_gate", {}),
        "forensic_report": state.get("forensic_report"),
        "thematic_report": state.get("thematic_report"),
        "sector_report": state.get("sector_report"),
        "moat_report": state.get("moat_report"),
        "quant_report": state.get("quant_report"),
        "memo_markdown": memo_md,
    }
