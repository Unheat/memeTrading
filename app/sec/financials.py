"""Deterministic SEC XBRL financial statements tool.

Extracts hard financial numbers directly from official SEC XBRL disclosures
via edgartools without vector RAG or LLM hallucination risk.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecFinancialsResult:
    """Deterministic quarterly financial ratios and statement values from SEC XBRL."""

    ticker: str
    status: str
    periods: tuple[str, ...]
    revenue: dict[str, float | None]
    gross_profit: dict[str, float | None]
    gross_margin_pct: dict[str, float | None]
    operating_income: dict[str, float | None]
    operating_margin_pct: dict[str, float | None]
    net_income: dict[str, float | None]
    cash_and_equivalents: dict[str, float | None]
    total_debt: dict[str, float | None]
    net_cash: dict[str, float | None]
    inventory: dict[str, float | None]
    inventory_qoq_change_pct: dict[str, float | None]
    capex: dict[str, float | None]
    provider: str
    as_of: str
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "ticker": self.ticker,
            "status": self.status,
            "periods": list(self.periods),
            "revenue": dict(self.revenue),
            "gross_profit": dict(self.gross_profit),
            "gross_margin_pct": dict(self.gross_margin_pct),
            "operating_income": dict(self.operating_income),
            "operating_margin_pct": dict(self.operating_margin_pct),
            "net_income": dict(self.net_income),
            "cash_and_equivalents": dict(self.cash_and_equivalents),
            "total_debt": dict(self.total_debt),
            "net_cash": dict(self.net_cash),
            "inventory": dict(self.inventory),
            "inventory_qoq_change_pct": dict(self.inventory_qoq_change_pct),
            "capex": dict(self.capex),
            "provider": self.provider,
            "as_of": self.as_of,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SecFinancialsResult:
        """Rebuild from dictionary."""
        return cls(
            ticker=str(data["ticker"]),
            status=str(data.get("status", "ok")),
            periods=tuple(str(p) for p in data.get("periods", [])),
            revenue=dict(data.get("revenue", {})),
            gross_profit=dict(data.get("gross_profit", {})),
            gross_margin_pct=dict(data.get("gross_margin_pct", {})),
            operating_income=dict(data.get("operating_income", {})),
            operating_margin_pct=dict(data.get("operating_margin_pct", {})),
            net_income=dict(data.get("net_income", {})),
            cash_and_equivalents=dict(data.get("cash_and_equivalents", {})),
            total_debt=dict(data.get("total_debt", {})),
            net_cash=dict(data.get("net_cash", {})),
            inventory=dict(data.get("inventory", {})),
            inventory_qoq_change_pct=dict(data.get("inventory_qoq_change_pct", {})),
            capex=dict(data.get("capex", {})),
            provider=str(data.get("provider", "sec_xbrl")),
            as_of=str(data.get("as_of", "")),
            error_message=str(data["error_message"]) if data.get("error_message") else None,
        )


def _is_period_col(col_name: Any) -> bool:
    """Check if a DataFrame column represents a fiscal date period."""
    s = str(col_name).strip()
    # e.g. 2024-06-30 or 2025-Q1
    if any(s.startswith(str(year)) for year in range(2000, 2040)):
        return True
    return False


def _sort_period_cols(cols: list[str]) -> list[str]:
    """Sort period columns in descending chronological order (newest first)."""
    return sorted(cols, reverse=True)


def _find_row_val(df: Any, concept_names: list[str], col: str) -> float | None:
    """Find a row matching concept_names and extract float value from column `col`."""
    if df is None:
        return None
    try:
        # Check index
        for concept in concept_names:
            concept_lower = concept.lower()
            for idx in df.index:
                if str(idx).lower() == concept_lower or concept_lower in str(idx).lower():
                    val = df.loc[idx, col]
                    if hasattr(val, "iloc"):
                        val = val.iloc[0]
                    if val is not None:
                        f_val = float(val)
                        return abs(f_val) if "payments" in concept_lower or "capex" in concept_lower else f_val
    except Exception:
        pass
    return None


def _get_company(ticker: str) -> Any:
    """Instantiate edgartools Company object."""
    from edgar import Company
    return Company(ticker)


def _fetch_xbrl_statements(ticker: str, periods: int = 4) -> dict[str, Any]:
    """Fetch raw statement series via edgartools with concept fallback."""
    from app.sec.identity import ensure_sec_identity
    ensure_sec_identity()

    company = _get_company(ticker)

    result: dict[str, Any] = {
        "periods": [],
        "revenue": {},
        "gross_profit": {},
        "operating_income": {},
        "net_income": {},
        "cash_and_equivalents": {},
        "total_debt": {},
        "inventory": {},
        "capex": {},
    }

    # 1. Income Statement
    try:
        inc_stmt = company.income_statement(annual=False, periods=periods, as_dataframe=True)
        if inc_stmt is not None and hasattr(inc_stmt, "columns"):
            period_cols = _sort_period_cols([str(c) for c in inc_stmt.columns if _is_period_col(c)])
            result["periods"] = period_cols[:periods]
            for col in result["periods"]:
                result["revenue"][col] = _find_row_val(inc_stmt, ["Revenues", "Revenue", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax"], col)
                result["gross_profit"][col] = _find_row_val(inc_stmt, ["GrossProfit", "GrossMargin"], col)
                result["operating_income"][col] = _find_row_val(inc_stmt, ["OperatingIncomeLoss", "OperatingIncome"], col)
                result["net_income"][col] = _find_row_val(inc_stmt, ["NetIncomeLoss", "NetIncome"], col)
    except Exception as exc:
        logger.debug("Failed income statement extraction via dataframe: %s", exc)

    # 2. Balance Sheet
    try:
        bs_stmt = company.balance_sheet(annual=False, periods=periods, as_dataframe=True)
        if bs_stmt is not None and hasattr(bs_stmt, "columns"):
            bs_periods = _sort_period_cols([str(c) for c in bs_stmt.columns if _is_period_col(c)])
            if not result["periods"]:
                result["periods"] = bs_periods[:periods]
            for col in result["periods"]:
                result["cash_and_equivalents"][col] = _find_row_val(bs_stmt, ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents", "Cash"], col)
                result["inventory"][col] = _find_row_val(bs_stmt, ["InventoryNet", "Inventories", "Inventory"], col)
                st_debt = _find_row_val(bs_stmt, ["ShortTermBorrowings", "CommercialPaper", "DebtCurrent"], col)
                lt_debt = _find_row_val(bs_stmt, ["LongTermDebtNoncurrent", "LongTermDebt"], col)
                if st_debt is not None or lt_debt is not None:
                    result["total_debt"][col] = (st_debt or 0.0) + (lt_debt or 0.0)
                else:
                    result["total_debt"][col] = None
    except Exception as exc:
        logger.debug("Failed balance sheet extraction via dataframe: %s", exc)

    # 3. Cash Flow Statement (CapEx)
    try:
        cf_stmt = company.cash_flow_statement(annual=False, periods=periods, as_dataframe=True)
        if cf_stmt is not None and hasattr(cf_stmt, "columns"):
            for col in result["periods"]:
                result["capex"][col] = _find_row_val(cf_stmt, ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets", "CapitalExpenditures"], col)
    except Exception as exc:
        logger.debug("Failed cash flow extraction via dataframe: %s", exc)

    if not result["periods"]:
        raise ValueError(f"No XBRL reporting periods found for ticker {ticker}")

    return result


def get_sec_financials(ticker: str, periods: int = 4) -> SecFinancialsResult:
    """Extract official quarterly SEC XBRL metrics with zero hallucination.

    :param ticker: Target company ticker (e.g. "MU").
    :param periods: Number of recent quarters to analyze (default 4).
    :returns: SecFinancialsResult with deterministic margins and inventory trends.
    """
    clean_ticker = ticker.upper().strip()
    as_of = datetime.now(timezone.utc).isoformat()

    try:
        raw = _fetch_xbrl_statements(clean_ticker, periods=periods)
    except Exception as exc:
        logger.warning("Failed to extract SEC XBRL financials for %s: %s", clean_ticker, exc)
        return SecFinancialsResult(
            ticker=clean_ticker,
            status="unavailable",
            periods=(),
            revenue={},
            gross_profit={},
            gross_margin_pct={},
            operating_income={},
            operating_margin_pct={},
            net_income={},
            cash_and_equivalents={},
            total_debt={},
            net_cash={},
            inventory={},
            inventory_qoq_change_pct={},
            capex={},
            provider="sec_xbrl",
            as_of=as_of,
            error_message=str(exc),
        )

    period_list = list(raw.get("periods", []))
    rev = raw.get("revenue", {})
    gp = raw.get("gross_profit", {})
    op_inc = raw.get("operating_income", {})
    net_inc = raw.get("net_income", {})
    cash = raw.get("cash_and_equivalents", {})
    debt = raw.get("total_debt", {})
    inv = raw.get("inventory", {})
    capex = raw.get("capex", {})

    gm_pct: dict[str, float | None] = {}
    opm_pct: dict[str, float | None] = {}
    net_cash: dict[str, float | None] = {}
    inv_qoq: dict[str, float | None] = {}

    for i, p in enumerate(period_list):
        # Gross Margin %
        r_val = rev.get(p)
        gp_val = gp.get(p)
        if r_val and gp_val and r_val > 0:
            gm_pct[p] = round(gp_val / r_val, 4)
        else:
            gm_pct[p] = None

        # Operating Margin %
        op_val = op_inc.get(p)
        if r_val and op_val and r_val > 0:
            opm_pct[p] = round(op_val / r_val, 4)
        else:
            opm_pct[p] = None

        # Net Cash (Cash - Debt)
        c_val = cash.get(p)
        d_val = debt.get(p)
        if c_val is not None and d_val is not None:
            net_cash[p] = round(c_val - d_val, 2)
        else:
            net_cash[p] = None

        # Inventory QoQ change %
        # period_list is newest-first e.g. [Q2, Q1, Q4, Q3], so prior quarter is i+1
        cur_inv = inv.get(p)
        if i + 1 < len(period_list):
            prior_p = period_list[i + 1]
            prior_inv = inv.get(prior_p)
            if cur_inv is not None and prior_inv and prior_inv > 0:
                inv_qoq[p] = round((cur_inv - prior_inv) / prior_inv, 4)
            else:
                inv_qoq[p] = None
        else:
            inv_qoq[p] = None

    return SecFinancialsResult(
        ticker=clean_ticker,
        status="ok",
        periods=tuple(period_list),
        revenue=rev,
        gross_profit=gp,
        gross_margin_pct=gm_pct,
        operating_income=op_inc,
        operating_margin_pct=opm_pct,
        net_income=net_inc,
        cash_and_equivalents=cash,
        total_debt=debt,
        net_cash=net_cash,
        inventory=inv,
        inventory_qoq_change_pct=inv_qoq,
        capex=capex,
        provider="sec_xbrl",
        as_of=as_of,
        error_message=None,
    )
