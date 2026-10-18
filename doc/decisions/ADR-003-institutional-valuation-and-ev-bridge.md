# ADR-003: Institutional Valuation & Capital Claims Bridge

## Status
Accepted

## Date
2026-10-18

## Context
Our financial computation engine in `app/sec/financials.py` and `app/valuation/calculator.mjs` contained foundational accounting and valuation flaws:
1. **Free Cash Flow Debt Double-Counting**: Free Cash Flow was computed as $\text{CFO} - \text{CapEx}$. Under US GAAP, CFO is calculated *after* deducting debt interest expense. The DCF engine discounted this cash flow at WACC (blended cost of capital) and then deducted net debt again in the Enterprise Value to Equity Value bridge, double-counting the debt burden.
2. **Missing Capital Structure Claims (ASC 842 / IFRS 16)**: Operating lease liabilities were omitted from total debt. For capital-intensive companies (foundries, cloud data centers, airlines, retail), lease obligations represent senior contractual claims. Preferred equity and minority interests were also omitted.
3. **Year-End Discounting Bias**: Discounting explicit cash flows with $(1 + r)^y$ assumed all cash arrived as a lump sum on the final day of the year, understating explicit cash flow present value by ~4%–5%.
4. **Reverse DCF Breakdown on Cyclicals**: Compounding trailing FCF in reverse DCF crashed or returned "N/A" whenever trailing FCF was negative or zero due to peak CapEx or cyclical downturns.

## Decision
Upgrade the valuation engine to institutional buyside hedge fund standards:
1. **Unlevered Free Cash Flow (FCFF)**:
   Extract `InterestExpense` and tax provisions from SEC XBRL disclosures to compute true Unlevered FCFF:
   $$\text{FCFF} = \text{CFO} + \text{Interest Expense} \times (1 - \text{Tax Rate}) - \text{CapEx}$$
   When discounting at WACC, this eliminates the debt double-counting flaw.
2. **Comprehensive Senior Capital Claims in EV Bridge**:
   Extract `OperatingLeaseLiabilityCurrent` and `Noncurrent` (ASC 842), `PreferredStockValue`, and `MinorityInterest` from SEC XBRL. Bridge Enterprise Value to Equity Value:
   $$\text{Equity Value} = \text{Enterprise Value} + \text{Net Cash} - \text{Operating Leases} - \text{Preferred Stock} - \text{Minority Interest}$$
3. **Mid-Year Discounting Convention**:
   Adopt standard buyside mid-year compounding for explicit cash flows:
   $$\text{PV}_y = \frac{\text{FCF}_y}{(1 + r)^{y - 0.5}}$$
4. **Michael Mauboussin Expectations Reverse DCF**:
   Adapt the Expectations Investing solver from `reference/implied-expectations` (`https://github.com/Keenan-ux/implied-expectations`). Invert stock prices into Implied Sales Growth and Implied NOPAT Margin using the growth-funding identity ($I = g / \text{ROIC}$), ensuring complete resilience when trailing FCF is negative.
5. **Cash Conversion Cycle (CCC)**:
   Extract Accounts Payable (`AccountsPayableTradeCurrent` / `AccountsPayableCurrent`) with fact-level fallback and calculate $\text{DPO} = \frac{\text{AP}}{\text{COGS}} \times 91.25$ and $\text{CCC} = \text{DIO} + \text{DSO} - \text{DPO}$.
6. **Quantitative Balance Sheet Health & Ratios**:
   Implement 5-factor manufacturing and 4-factor service/tech Altman Z-Score models, 5-stage DuPont ROE decomposition, and ROIC vs. WACC Economic Value Added (EVA) spread.

## Alternatives Considered

### Treating FCF as Levered FCFE (Free Cash Flow to Equity)
- Pros: Avoids extracting interest expense.
- Cons: Requires estimating dynamic Cost of Equity ($K_e$) for each period, cannot add or subtract cash balance in EV bridge, and makes cross-capital structure comparisons difficult.
- Rejected: Unlevered FCFF discounted at WACC is the universal standard for corporate enterprise valuation.

### Retaining Constant-Growth Trailing FCF Bisection
- Pros: Simple code loop.
- Cons: Completely unworkable for cyclical companies at trough earnings or high-growth tech companies reinvesting aggressively into infrastructure.
- Rejected: Cannot support memory, foundry, semiconductor, or cloud infrastructure research.

## Consequences
- Clean mathematical valuation bridge eliminating debt double-counting and lease understatements.
- Full analytical support for cyclical companies undergoing CapEx expansions.
- Comprehensive working capital and balance sheet health telemetry available to analysts and the Investment Committee.
