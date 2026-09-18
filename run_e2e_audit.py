"""End-to-end audit runner for deep research pipeline."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Configure detailed logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logging.getLogger("app").setLevel(logging.INFO)
logging.getLogger("app.agent").setLevel(logging.INFO)

from app.agent.runner import run_investigation
from app.agent.state import BudgetLimits, ResearchRequest
from app.config import load_config


def main():
    print("=" * 80)
    print("STARTING E2E DEEP RESEARCH INVESTIGATION AUDIT")
    print("Mandate: 'find me best 2 tech stock to invest right now'")
    print("=" * 80)

    cfg = load_config()
    req = ResearchRequest(
        query="find me best 2 tech stock to invest right now",
        requested_ranking_count=2,
        budget=BudgetLimits(max_total_tool_calls=25, max_identical_calls=2),
    )

    try:
        result = run_investigation(
            request=req,
            generate_media=False,
            config=cfg,
        )

        print("\n" + "=" * 80)
        print("INVESTIGATION COMPLETED SUCCESSFULLY")
        print("=" * 80)
        print(f"Case ID: {result.case_id}")
        print(f"Status: {result.status}")
        print(f"Ticker: {result.ticker}")
        print(f"Tool calls executed: {result.final_state.get('tool_calls')}")
        print(f"Candidates registered: {list((result.final_state.get('candidates') or {}).keys())}")
        print(f"Work queue items: {len(result.final_state.get('work_queue') or [])}")
        print(f"Receipts logged: {len(result.final_state.get('searches_performed') or [])}")
        print(f"Comparisons generated: {len(result.final_state.get('comparisons') or [])}")

        for cid, cand in (result.final_state.get("candidates") or {}).items():
            print(f"\n--- Candidate: {cid} (${cand.get('ticker')}) ---")
            print(f"Status: {cand.get('status')}")
            print(f"Has market context: {bool(cand.get('market_context'))}")
            print(f"Has SEC financials: {bool(cand.get('sec_financials'))}")
            print(f"Has diligence dossier: {bool(cand.get('diligence_dossier'))}")
            print(f"Has valuation: {bool(cand.get('valuation'))}")

        print("\n" + "=" * 80)
        print("MEMO PREVIEW (First 2000 chars):")
        print("=" * 80)
        print(result.memo_markdown[:2000])

    except Exception as exc:
        print("\n" + "!" * 80)
        print(f"INVESTIGATION FAILED WITH EXCEPTION: {exc}")
        print("!" * 80)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
