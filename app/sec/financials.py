"""Deterministic SEC XBRL financial statements tool.

Extracts hard financial numbers directly from official SEC XBRL disclosures
via edgartools without vector RAG or LLM hallucination risk.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
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
    cash_from_operations: dict[str, float | None]
    capex: dict[str, float | None]
    provider: str
    as_of: str
    error_message: str | None = None
    total_assets: dict[str, float | None] = field(default_factory=dict)
    accounts_receivable: dict[str, float | None] = field(default_factory=dict)
    current_assets: dict[str, float | None] = field(default_factory=dict)
    ppe: dict[str, float | None] = field(default_factory=dict)
    depreciation: dict[str, float | None] = field(default_factory=dict)
    sg_and_a: dict[str, float | None] = field(default_factory=dict)
    stock_based_compensation: dict[str, float | None] = field(default_factory=dict)
    current_liabilities: dict[str, float | None] = field(default_factory=dict)
    fcf: dict[str, float | None] = field(default_factory=dict)
    ttm_fcf: float | None = None

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
            "cash_from_operations": dict(self.cash_from_operations),
            "capex": dict(self.capex),
            "provider": self.provider,
            "as_of": self.as_of,
            "error_message": self.error_message,
            "total_assets": dict(self.total_assets),
            "accounts_receivable": dict(self.accounts_receivable),
            "current_assets": dict(self.current_assets),
            "ppe": dict(self.ppe),
            "depreciation": dict(self.depreciation),
            "sg_and_a": dict(self.sg_and_a),
            "stock_based_compensation": dict(self.stock_based_compensation),
            "current_liabilities": dict(self.current_liabilities),
            "fcf": dict(self.fcf),
            "ttm_fcf": self.ttm_fcf,
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
            cash_from_operations=dict(data.get("cash_from_operations", {})),
            capex=dict(data.get("capex", {})),
            provider=str(data.get("provider", "sec_xbrl")),
            as_of=str(data.get("as_of", "")),
            error_message=str(data["error_message"]) if data.get("error_message") else None,
            total_assets=dict(data.get("total_assets", {})),
            accounts_receivable=dict(data.get("accounts_receivable", {})),
            current_assets=dict(data.get("current_assets", {})),
            ppe=dict(data.get("ppe", {})),
            depreciation=dict(data.get("depreciation", {})),
            sg_and_a=dict(data.get("sg_and_a", {})),
            stock_based_compensation=dict(data.get("stock_based_compensation", {})),
            current_liabilities=dict(data.get("current_liabilities", {})),
            fcf=dict(data.get("fcf", {})),
            ttm_fcf=float(data["ttm_fcf"]) if data.get("ttm_fcf") is not None else None,
        )


def _is_period_col(col_name: Any) -> bool:
    """Check if a DataFrame column represents a fiscal date period."""
    s = str(col_name).strip()
    # e.g. 2024-06-30, 2025-Q1, Q3 2026, FY 2025
    if any(str(year) in s for year in range(2000, 2040)):
        return True
    return False


def _sort_period_cols(cols: list[str]) -> list[str]:
    """Sort period columns in descending chronological order (newest first)."""
    import re

    def _parse_key(col: str):
        c = str(col).strip()
        m_q = re.search(r"Q([1-4])\s*(\d{4})", c, re.I)
        if m_q:
            return (int(m_q.group(2)), int(m_q.group(1)), c)
        m_yq = re.search(r"(\d{4})\s*[-Q]\s*([1-4])", c, re.I)
        if m_yq:
            return (int(m_yq.group(1)), int(m_yq.group(2)), c)
        m_date = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", c)
        if m_date:
            return (int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3)))
        m_fy = re.search(r"(\d{4})", c)
        if m_fy:
            return (int(m_fy.group(1)), 0, c)
        return (0, 0, c)

    return sorted(cols, key=_parse_key, reverse=True)


def _period_col_after_as_of(col: str, as_of_str: str | None) -> bool:
    """Return True if a period column represents a date strictly after as_of_str (lookahead)."""
    if not as_of_str:
        return False
    import re
    from datetime import date
    try:
        as_of_d = date.fromisoformat(str(as_of_str)[:10])
    except Exception:
        return False
    c = str(col).strip()
    m_date = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", c)
    if m_date:
        try:
            col_d = date(int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3)))
            return col_d > as_of_d
        except ValueError:
            pass
    m_q = re.search(r"Q([1-4])\s*(\d{4})", c, re.I)
    if m_q:
        q_year = int(m_q.group(2))
        if q_year > as_of_d.year:
            return True
        if q_year == as_of_d.year:
            q_num = int(m_q.group(1))
            as_of_q = (as_of_d.month - 1) // 3 + 1
            return q_num > as_of_q
    m_yq = re.search(r"(\d{4})\s*[-Q]\s*([1-4])", c, re.I)
    if m_yq:
        q_year = int(m_yq.group(1))
        if q_year > as_of_d.year:
            return True
        if q_year == as_of_d.year:
            q_num = int(m_yq.group(2))
            as_of_q = (as_of_d.month - 1) // 3 + 1
            return q_num > as_of_q
    m_fy = re.search(r"(\d{4})", c)
    if m_fy:
        return int(m_fy.group(1)) > as_of_d.year
    return False


def _find_row_val(df: Any, concept_names: list[str], col: str) -> float | None:
    """Find a matching concept's finite numeric value, otherwise return ``None``.

    Performs exact concept match first across candidates, then falls back to prefix/contains.

    :param df: Statement dataframe indexed by SEC XBRL concept.
    :param concept_names: Ordered candidate concepts, from preferred to fallback.
    :param col: Fiscal-period column name.
    :returns: Matching finite value, with CapEx payments made positive, or ``None``.
    """
    if df is None or not hasattr(df, "columns") or col not in df.columns:
        return None
    try:
        df_index_lower = [str(idx).lower() for idx in df.index]
        # 1. Exact matches in priority order
        for concept in concept_names:
            c_low = concept.lower()
            if c_low in df_index_lower:
                idx = df.index[df_index_lower.index(c_low)]
                val = df.loc[idx, col]
                if hasattr(val, "iloc"):
                    val = val.iloc[0]
                if val is not None:
                    f_val = float(val)
                    if math.isfinite(f_val):
                        return abs(f_val) if "payments" in c_low or "capex" in c_low else f_val

        # 2. Substring matches in priority order
        for concept in concept_names:
            c_low = concept.lower()
            for i, idx_str in enumerate(df_index_lower):
                if c_low in idx_str:
                    idx = df.index[i]
                    val = df.loc[idx, col]
                    if hasattr(val, "iloc"):
                        val = val.iloc[0]
                    if val is not None:
                        f_val = float(val)
                        if math.isfinite(f_val):
                            return abs(f_val) if "payments" in c_low or "capex" in c_low else f_val
    except Exception:
        pass
    return None


def _resolve_bs_dataframe_and_col(col: str, bs_q: Any, bs_a: Any) -> tuple[Any, str | None]:
    """Resolve the appropriate balance sheet dataframe and column for a fiscal period.

    SEC Form 10-Q covers Q1-Q3; Q4 point-in-time metrics are filed on Form 10-K under FY.
    """
    import re

    # 1. If present in quarterly balance sheet, use it
    if bs_q is not None and hasattr(bs_q, "columns") and col in bs_q.columns:
        return bs_q, col

    # 2. If present directly in annual balance sheet, use it
    if bs_a is not None and hasattr(bs_a, "columns") and col in bs_a.columns:
        return bs_a, col

    # 3. If period is Q4 <YYYY> (or <YYYY>-Q4), map to FY <YYYY> in annual balance sheet
    m_q4 = re.search(r"Q4\s*(\d{4})", str(col), re.I) or re.search(r"(\d{4})\s*[-Q]\s*4", str(col), re.I)
    if m_q4 and bs_a is not None and hasattr(bs_a, "columns"):
        year = m_q4.group(1)
        fy_col = f"FY {year}"
        if fy_col in bs_a.columns:
            return bs_a, fy_col
        for c in bs_a.columns:
            if year in str(c):
                return bs_a, str(c)

    return None, None


def _find_bs_metric(
    concept_names: list[str],
    col: str,
    bs_q: Any,
    bs_a: Any,
    fallback_cols: list[str] | None = None,
) -> float | None:
    """Find a balance sheet metric for a period with 10-K FY and prior-quarter fallback."""
    df, matched_col = _resolve_bs_dataframe_and_col(col, bs_q, bs_a)
    if df is not None and matched_col:
        val = _find_row_val(df, concept_names, matched_col)
        if val is not None:
            return val

    # If not found and fallback columns provided, check most recent available period
    if fallback_cols:
        for f_col in fallback_cols:
            if f_col == col:
                continue
            f_df, f_matched_col = _resolve_bs_dataframe_and_col(f_col, bs_q, bs_a)
            if f_df is not None and f_matched_col:
                f_val = _find_row_val(f_df, concept_names, f_matched_col)
                if f_val is not None:
                    return f_val
    return None


def _decumulate_cash_flows(periods: list[str], series: dict[str, float | None]) -> dict[str, float | None]:
    """Convert cumulative YTD cash flow statement periods into discrete quarters if needed.

    SEC Form 10-Q filings report cash flow on a cumulative year-to-date basis:
      Q1: 3-month discrete (~90 days)
      Q2: 6-month cumulative (~180 days)
      Q3: 9-month cumulative (~270 days)
      Q4: 12-month annual (Form 10-K)

    If the series exhibits monotonic cumulative YTD growth within a fiscal year,
    this derives discrete quarterly values:
      Q2_discrete = Q2_cumulative - Q1
      Q3_discrete = Q3_cumulative - Q2_cumulative
      Q4_discrete = Q4_cumulative - Q3_cumulative
    """
    if not periods or not series:
        return dict(series)

    result = dict(series)
    import re
    from collections import defaultdict

    def _extract_fy_and_q(p_str: str) -> tuple[int | None, int | None]:
        m_q = re.search(r"Q([1-4])[-_\s]*(\d{4})", p_str, re.I)
        if m_q:
            return int(m_q.group(2)), int(m_q.group(1))
        m_yq = re.search(r"(\d{4})[-_\s]*Q?([1-4])", p_str, re.I)
        if m_yq:
            return int(m_yq.group(1)), int(m_yq.group(2))
        m_date = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", p_str)
        if m_date:
            year, month = int(m_date.group(1)), int(m_date.group(2))
            q = (month - 1) // 3 + 1
            return year, q
        m_fy = re.search(r"(\d{4})", p_str)
        if m_fy:
            return int(m_fy.group(1)), None
        return None, None

    by_year: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for p in periods:
        fy, q = _extract_fy_and_q(p)
        if fy is not None and q is not None:
            by_year[fy].append((q, p))

    for fy, q_list in by_year.items():
        q_list.sort(key=lambda item: item[0])
        if len(q_list) < 2:
            continue

        vals = [result.get(p) for _, p in q_list]
        is_cumulative = False

        if all(v is not None and v > 0 for v in vals):
            if len(vals) >= 2 and vals[0] > 0 and vals[1] >= 1.5 * vals[0]:
                is_cumulative = True
            elif len(vals) >= 3 and vals[1] > 0 and vals[2] >= 1.3 * vals[1]:
                is_cumulative = True

        if is_cumulative:
            for idx in range(len(q_list) - 1, 0, -1):
                cur_q, cur_p = q_list[idx]
                prev_q, prev_p = q_list[idx - 1]
                cur_val = result.get(cur_p)
                prev_val = result.get(prev_p)
                if cur_val is not None and prev_val is not None:
                    discrete_val = round(cur_val - prev_val, 2)
                    if discrete_val >= 0:
                        result[cur_p] = discrete_val

    return result


def _get_company(ticker: str) -> Any:
    """Instantiate edgartools Company object."""
    from edgar import Company
    return Company(ticker)


def _fetch_xbrl_statements(ticker: str, periods: int = 4, as_of_date: str | None = None) -> dict[str, Any]:
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
        "cash_from_operations": {},
        "capex": {},
        "total_assets": {},
        "accounts_receivable": {},
        "current_assets": {},
        "ppe": {},
        "depreciation": {},
        "sg_and_a": {},
        "stock_based_compensation": {},
        "current_liabilities": {},
    }

    # 1. Income Statement
    try:
        inc_stmt = company.income_statement(annual=False, periods=periods, as_dataframe=True)
        if inc_stmt is not None and hasattr(inc_stmt, "columns"):
            period_cols = [c for c in _sort_period_cols([str(c) for c in inc_stmt.columns if _is_period_col(c)]) if not _period_col_after_as_of(c, as_of_date)]
            result["periods"] = period_cols[:periods]
            for col in result["periods"]:
                result["revenue"][col] = _find_row_val(inc_stmt, ["Revenues", "Revenue", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax"], col)
                result["gross_profit"][col] = _find_row_val(inc_stmt, ["GrossProfit", "GrossMargin"], col)
                result["operating_income"][col] = _find_row_val(inc_stmt, ["OperatingIncomeLoss", "OperatingIncome"], col)
                result["net_income"][col] = _find_row_val(inc_stmt, ["NetIncomeLoss", "NetIncome"], col)
                result["sg_and_a"][col] = _find_row_val(inc_stmt, ["SellingGeneralAndAdministrativeExpense", "GeneralAndAdministrativeExpense", "SellingAndMarketingExpense", "SellingExpense", "AdministrativeExpense"], col)
    except Exception as exc:
        logger.debug("Failed income statement extraction via dataframe: %s", exc)

    # 2. Balance Sheet (Fetch both quarterly 10-Q and annual 10-K)
    bs_q = None
    bs_a = None
    try:
        bs_q = company.balance_sheet(annual=False, periods=periods, as_dataframe=True)
    except Exception as exc:
        logger.debug("Failed quarterly balance sheet extraction via dataframe: %s", exc)

    try:
        bs_a = company.balance_sheet(annual=True, periods=periods, as_dataframe=True)
    except Exception as exc:
        logger.debug("Failed annual balance sheet extraction via dataframe: %s", exc)

    if not result["periods"] and bs_q is not None and hasattr(bs_q, "columns"):
        result["periods"] = [c for c in _sort_period_cols([str(c) for c in bs_q.columns if _is_period_col(c)]) if not _period_col_after_as_of(c, as_of_date)][:periods]

    period_cols_available = list(result["periods"])
    for col in result["periods"]:
        # A. Liquid Cash: Check combined cash & short-term investments first, then base cash + short-term investments
        cash_comb = _find_bs_metric(["CashCashEquivalentsAndShortTermInvestments"], col, bs_q, bs_a, fallback_cols=period_cols_available)
        if cash_comb is not None:
            result["cash_and_equivalents"][col] = cash_comb
        else:
            base_cash = _find_bs_metric(
                ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents", "Cash", "CashAndDueFromBanks"],
                col, bs_q, bs_a, fallback_cols=period_cols_available,
            )
            st_inv = _find_bs_metric(
                ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "MarketableSecurities"],
                col, bs_q, bs_a, fallback_cols=period_cols_available,
            )
            if base_cash is not None or st_inv is not None:
                result["cash_and_equivalents"][col] = (base_cash or 0.0) + (st_inv or 0.0)
            else:
                result["cash_and_equivalents"][col] = None

        # B. Inventory
        result["inventory"][col] = _find_bs_metric(
            ["InventoryNet", "Inventories", "Inventory", "InventoryGross"],
            col, bs_q, bs_a, fallback_cols=period_cols_available,
        )

        # C. Total Debt: Sum current and long-term debt, or use combined total debt concept
        st_debt = _find_bs_metric(
            ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings", "CommercialPaper", "NotesPayableCurrent", "ConvertibleDebtCurrent"],
            col, bs_q, bs_a, fallback_cols=period_cols_available,
        )
        lt_debt = _find_bs_metric(
            ["LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations", "LongTermNotesAndLoans", "LongTermBorrowings"],
            col, bs_q, bs_a, fallback_cols=period_cols_available,
        )
        if st_debt is not None or lt_debt is not None:
            result["total_debt"][col] = (st_debt or 0.0) + (lt_debt or 0.0)
        else:
            comb_debt = _find_bs_metric(
                ["DebtLongtermAndShorttermCombinedAmount", "DebtInstrumentCarryingAmount", "TotalDebt"],
                col, bs_q, bs_a, fallback_cols=period_cols_available,
            )
            result["total_debt"][col] = comb_debt

        # D. Forensic Balance Sheet Concepts
        result["total_assets"][col] = _find_bs_metric(["Assets", "AssetsCurrentAndNoncurrent"], col, bs_q, bs_a, fallback_cols=period_cols_available)
        result["accounts_receivable"][col] = _find_bs_metric(["AccountsReceivableNetCurrent", "ReceivablesNetCurrent", "AccountsNotesAndLoansReceivableNetCurrent", "AccountsReceivableNet"], col, bs_q, bs_a, fallback_cols=period_cols_available)
        result["current_assets"][col] = _find_bs_metric(["AssetsCurrent"], col, bs_q, bs_a, fallback_cols=period_cols_available)
        result["ppe"][col] = _find_bs_metric(["PropertyPlantAndEquipmentNet", "PropertyPlantAndEquipmentGross"], col, bs_q, bs_a, fallback_cols=period_cols_available)
        result["current_liabilities"][col] = _find_bs_metric(["LiabilitiesCurrent"], col, bs_q, bs_a, fallback_cols=period_cols_available)

    # 3. Cash Flow Statement (CFO, CapEx, Depreciation, SBC)
    try:
        cf_stmt = company.cash_flow_statement(annual=False, periods=periods, as_dataframe=True)
        if cf_stmt is not None and hasattr(cf_stmt, "columns"):
            for col in result["periods"]:
                result["cash_from_operations"][col] = _find_row_val(cf_stmt, ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByOperatingActivities", "OperatingCashFlow"], col)
                result["capex"][col] = _find_row_val(cf_stmt, ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets", "CapitalExpenditures"], col)
                result["depreciation"][col] = _find_row_val(cf_stmt, ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "Depreciation", "DepreciationAmortizationAndAccretionNet"], col)
                result["stock_based_compensation"][col] = _find_row_val(cf_stmt, ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense", "StockOptionExpense", "ShareBasedPaymentArrangementNoncashExpense"], col)
    except Exception as exc:
        logger.debug("Failed cash flow extraction via dataframe: %s", exc)

    # De-cumulate cash flows if reported on cumulative YTD basis in 10-Q
    result["cash_from_operations"] = _decumulate_cash_flows(result["periods"], result["cash_from_operations"])
    result["capex"] = _decumulate_cash_flows(result["periods"], result["capex"])
    result["depreciation"] = _decumulate_cash_flows(result["periods"], result["depreciation"])
    result["stock_based_compensation"] = _decumulate_cash_flows(result["periods"], result["stock_based_compensation"])

    if not result["periods"]:
        raise ValueError(f"No XBRL reporting periods found for ticker {ticker}")

    return result


def get_sec_financials(ticker: str, periods: int = 4, as_of_date: str | None = None) -> SecFinancialsResult:
    """Extract official quarterly SEC XBRL metrics with zero hallucination.

    :param ticker: Target company ticker (e.g. "MU").
    :param periods: Number of recent quarters to analyze (default 4).
    :param as_of_date: Optional PIT cutoff (YYYY-MM-DD); periods filed after this date are excluded.
    :returns: SecFinancialsResult with deterministic margins and inventory trends.
    """
    clean_ticker = ticker.upper().strip()
    as_of = as_of_date or datetime.now(timezone.utc).isoformat()

    try:
        raw = _fetch_xbrl_statements(clean_ticker, periods=periods, as_of_date=as_of_date)
    except Exception as exc:
        logger.warning("Failed to extract SEC XBRL financials for %s: %s", clean_ticker, exc)
        is_foreign = False
        try:
            from edgar import Company
            comp = Company(clean_ticker)
            filings = comp.get_filings(form=["20-F", "6-K"])
            if filings and len(filings) > 0:
                is_foreign = True
        except Exception:
            pass

        if is_foreign:
            return SecFinancialsResult(
                ticker=clean_ticker,
                status="ok_foreign_issuer_unstructured",
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
                cash_from_operations={},
                capex={},
                provider="sec_edgar_foreign",
                as_of=as_of,
                error_message="Foreign Private Issuer reports under IFRS via Form 20-F/6-K (no standard US-GAAP XBRL). Use search_sec_evidence, read_sec_evidence, or company research fundamentals for financial metrics.",
            )

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
            cash_from_operations={},
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
    cfo = raw.get("cash_from_operations", {})
    capex = raw.get("capex", {})
    tot_assets = raw.get("total_assets", {})
    ar = raw.get("accounts_receivable", {})
    ca = raw.get("current_assets", {})
    ppe_val = raw.get("ppe", {})
    depr = raw.get("depreciation", {})
    sga = raw.get("sg_and_a", {})
    sbc = raw.get("stock_based_compensation", {})
    cl = raw.get("current_liabilities", {})

    gm_pct: dict[str, float | None] = {}
    opm_pct: dict[str, float | None] = {}
    net_cash: dict[str, float | None] = {}
    inv_qoq: dict[str, float | None] = {}
    fcf: dict[str, float | None] = {}

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

        # Free Cash Flow (CFO - CapEx)
        cf_val = cfo.get(p)
        cx_val = capex.get(p)
        if cf_val is not None and cx_val is not None:
            fcf[p] = round(cf_val - cx_val, 2)
        else:
            fcf[p] = None

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

    # Calculate TTM FCF: sum of up to 4 most recent discrete quarters
    valid_fcfs = [fcf[p] for p in period_list[:4] if fcf.get(p) is not None]
    if len(valid_fcfs) == 4:
        ttm_fcf = round(sum(valid_fcfs), 2)
    elif len(valid_fcfs) >= 1:
        ttm_fcf = round(valid_fcfs[0] * 4.0, 2)
    else:
        ttm_fcf = None

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
        cash_from_operations=cfo,
        capex=capex,
        provider="sec_xbrl",
        as_of=as_of,
        error_message=None,
        total_assets=tot_assets,
        accounts_receivable=ar,
        current_assets=ca,
        ppe=ppe_val,
        depreciation=depr,
        sg_and_a=sga,
        stock_based_compensation=sbc,
        current_liabilities=cl,
        fcf=fcf,
        ttm_fcf=ttm_fcf,
    )
