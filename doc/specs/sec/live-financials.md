# Module Spec — Live Financials Extraction (`app/sec/financials.py`)

## Responsibility

Extract live quarterly financial statements and metrics from official SEC EDGAR XBRL disclosures using `edgartools` with fallback to SEC company facts.

## Requirements

1. **Auto-Identity**: Ensure `ensure_sec_identity()` is called before creating `edgar.Company(ticker)`.
2. **Multi-Period Extraction**:
   - Query quarterly (non-annual) statements:
     - `company.income_statement(annual=False, periods=periods, as_dataframe=True)`
     - `company.balance_sheet(annual=False, periods=periods, as_dataframe=True)`
     - `company.cash_flow_statement(annual=False, periods=periods, as_dataframe=True)`
   - Extract:
     - Revenue (`Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet`)
     - Gross Profit (`GrossProfit`)
     - Operating Income (`OperatingIncomeLoss`)
     - Net Income (`NetIncomeLoss`)
     - Cash & Equivalents (`CashAndCashEquivalentsAtCarryingValue`)
     - Total Debt (`ShortTermBorrowings` + `LongTermDebtNoncurrent`)
     - Inventory (`InventoryNet`)
     - Cash From Operations (`NetCashProvidedByUsedInOperatingActivities`)
     - CapEx (`PaymentsToAcquirePropertyPlantAndEquipment`)
3. **Normalized consumer contract**: Successful tool payloads retain each extracted period series unchanged. Pandas/NumPy non-finite values (`NaN`, positive infinity, negative infinity) are normalized to `null`; matching continues to later candidate rows so abstract statement rows cannot mask a concrete value. Downstream derives FCF only as same-period CFO minus CapEx; absent values are retained as `null` and must not be estimated.
4. **CFO aliases**: Cash-from-operations lookup prioritizes `NetCashProvidedByUsedInOperatingActivities` and supports `NetCashProvidedByOperatingActivities` and `OperatingCashFlow`; abstract rows are excluded because they are structural labels, not reported values.
5. **Graceful Fallback**: If multi-period statements are empty or raise an error, fall back to `company.get_facts()` concepts or return clean `status="unavailable"` without crashing.

## Donor Code Provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.sec.financials._fetch_xbrl_statements` | adapted | `reference/edgartools/edgar/entity/core.py:1027-1071` | Uses quarterly income, balance-sheet, and cash-flow statements with local multi-concept alias resolution for robust accounting series; adds CFO extraction for source-only FCF derivation. |
