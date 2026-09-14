"""End-to-end smoke test validating the complete 3-stage pipeline and all components."""
from pathlib import Path
import json
import pytest
from unittest.mock import patch
from langchain_core.messages import AIMessage, HumanMessage

from app.sec.identity import ensure_sec_identity
from app.sec.form4 import parse_form4_xml, Form4AuditSummary
from app.sec.financials import get_sec_financials, SecFinancialsResult
from app.market.metrics import compute_fractional_kelly, average_daily_dollar_volume, market_cap_tier
from app.agent.state import ResearchRequest
from app.agent.runner import run_investigation, InvestigationResult
from app.media.faceless_bridge import FacelessBridge

SAMPLE_FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
    <issuer><issuerTradingSymbol>MU</issuerTradingSymbol></issuer>
    <periodOfReport>2026-09-01</periodOfReport>
    <reportingOwner>
        <reportingOwnerId><rptOwnerName>Sanjay Mehrotra</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>1</isOfficer><officerTitle>CEO</officerTitle></reportingOwnerRelationship>
    </reportingOwner>
    <aff10b5One>1</aff10b5One>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <transactionDate><value>2026-09-01</value></transactionDate>
            <transactionCoding><transactionCode>F</transactionCode></transactionCoding>
            <transactionAmounts>
                <transactionShares><value>45000</value></transactionShares>
                <transactionPricePerShare><value>118.50</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
</ownershipDocument>
"""


class FullPipelineTestModel:
    """Deterministic offline model for end-to-end pipeline smoke test."""

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        last_msg = messages[-1] if messages else None
        content = getattr(last_msg, "content", "")

        if "Conduct a hostile short-seller red team attack" in content:
            return AIMessage(content="""{
  "falsifiable_objections": [
    "DDR5 spot price premiums will compress as competitors ramp 1b nodes.",
    "Capex of $12B will depress normalized FCF margin below 15%."
  ],
  "numeric_kill_criteria": [
    "Kill Trigger 1: Gross margin contracts below 30% in next 10-Q.",
    "Kill Trigger 2: Inventory DSI increases by more than 15 days QoQ."
  ],
  "bear_floor_price": 75.0,
  "bear_thesis_summary": "Cyclical peak multiple trap."
}""")
        elif "Review the investment case for" in content:
            return AIMessage(content="CIO IC Verdict: Approved long position with 8.0% Quarter-Kelly allocation.")
        elif "Write an institutional, deeply cited forensic research article" in content:
            return AIMessage(content="""# The DDR5 Shortage Is Real — And Micron's 10-Q Proves Who Wins

**Bottom Line**: Retail memory shortages are translating into expanding margins [1].

## SEC Audit & Receipts
According to Micron's Form 10-Q [1], gross margins expanded to 36%.

## Primary Sources
[1] Form 10-Q, Accession 0001193125-26-123456, https://www.sec.gov/123""")
        elif "Create the 60–75 second viral dialogue reel" in content:
            return AIMessage(content="""```json
[
  {"index": 0, "voiceId": "e34b4e061b874623a08f41e5c4fecfb9", "text": "(shocked) You're saying RAM prices are surging?"},
  {"index": 1, "voiceId": "fdffd3722cd040fcb3f95eec5a7f29f3", "text": "(smirking) Yes, and Micron raised prices by 35%."},
  {"index": 2, "voiceId": "e34b4e061b874623a08f41e5c4fecfb9", "text": "(curious) But did Wall Street notice?"},
  {"index": 3, "voiceId": "fdffd3722cd040fcb3f95eec5a7f29f3", "text": "(laughing) No, consensus is flat. Check the full audit below!"}
]
```
CAPTION:
DDR5 memory is vanishing. Wall Street is asleep. 🚨 Full audit in bio. #stocks #investing""")
        else:
            # Stage 1: Investigator turn
            # If tool response message is already present in history:
            has_tool_res = any(
                getattr(m, "type", "") == "tool" or getattr(m, "tool_call_id", None)
                for m in messages
            )
            if has_tool_res:
                return AIMessage(
                    content="Forensic findings: Micron has strong DDR5 demand verified by market and SEC data."
                )
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_market_data",
                        "args": {"ticker": "MU"},
                        "id": "call_market",
                        "type": "tool_call",
                    }
                ],
            )


def test_complete_end_to_end_pipeline_smoke(tmp_path: Path):
    # 1. Test SEC identity initialization
    ident = ensure_sec_identity()
    assert "@" in ident

    # 2. Test Form 4 XML parser isolates Code F tax withholding
    f4_summary = parse_form4_xml(SAMPLE_FORM4_XML)
    assert f4_summary.tax_withholding_shares == 45000.0
    assert f4_summary.open_market_sales_shares == 0.0
    assert f4_summary.rule_10b5_1_active is True

    # 3. Test Fractional Kelly sizing
    kelly = compute_fractional_kelly(upside_pct=0.45, downside_pct=0.15, win_prob=0.60, fraction=0.25)
    assert kelly == pytest.approx(0.08)

    # 4. Run end-to-end investigation with 3-stage pipeline & media package
    fake_hist = {
        "dates": [f"2026-09-{i:02d}" for i in range(1, 26)],
        "open": [100.0] * 25,
        "high": [105.0] * 25,
        "low": [95.0] * 25,
        "close": [100.0] * 25,
        "volume": [500_000.0] * 25,  # 100 * 500k = $50M/day ADDV
    }
    fake_info = {
        "market_cap": 140e9,
        "shares_outstanding": 1.1e9,
        "short_interest_pct": 2.5,
        "currency": "USD",
        "exchange": "NASDAQ",
    }

    req = ResearchRequest(query="Investigate MU DDR5 shortage", ticker="MU", company="Micron Technology Inc")
    with patch("app.market.market_data.fetch_history", return_value=fake_hist), \
         patch("app.market.market_data.fetch_info", return_value=fake_info):
        result = run_investigation(
            request=req,
            model=FullPipelineTestModel(),
            cases_root=tmp_path,
            generate_media=True,
        )

    assert isinstance(result, InvestigationResult)
    assert result.ticker == "MU"
    assert result.status == "completed"

    # Verify all case disk files
    case_dir = tmp_path / result.case_id
    assert case_dir.exists()
    assert (case_dir / "memo.md").exists()
    assert (case_dir / "investigation.json").exists()
    assert (case_dir / "article.md").exists()
    assert (case_dir / "faceless" / "dialogue.json").exists()
    assert (case_dir / "faceless" / "caption.txt").exists()

    # Verify memo contents
    memo_text = (case_dir / "memo.md").read_text(encoding="utf-8")
    assert "Real-Money Capital Safety & Tradability Scorecard" in memo_text
    assert "3:1 Asymmetry Hurdle" in memo_text
    assert "IC Conviction Tier" in memo_text
    assert "Adversarial Red Team Invalidation" in memo_text
    assert "Kill Trigger 1" in memo_text

    # Verify article contents
    article_text = (case_dir / "article.md").read_text(encoding="utf-8")
    assert "[1]" in article_text
    assert "0001193125-26-123456" in article_text

    # Verify faceless dialogue contents
    dialogue_data = json.loads((case_dir / "faceless" / "dialogue.json").read_text(encoding="utf-8"))
    assert len(dialogue_data) == 4
    assert dialogue_data[0]["voiceId"] == "e34b4e061b874623a08f41e5c4fecfb9"
    assert dialogue_data[1]["voiceId"] == "fdffd3722cd040fcb3f95eec5a7f29f3"
    assert "(shocked)" in dialogue_data[0]["text"]

    # 5. Verify Faceless Bridge readiness
    bridge = FacelessBridge()
    doctor = bridge.check_doctor()
    assert isinstance(doctor, dict)
    assert "node_ready" in doctor
