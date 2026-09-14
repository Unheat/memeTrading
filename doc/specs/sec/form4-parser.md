# Module Spec — `app/sec/form4.py`

## Responsibility

Deterministic extraction of SEC Form 4 XML filings into structured insider trading records without vector RAG or LLM hallucination risk. Explicitly isolates Code F statutory tax withholding on RSU vesting and detects Rule 10b5-1 pre-scheduled trading plans.

## Public Contracts

### `Form4Transaction`
- `insider_name: str`
- `position: str` (e.g. `"Director"`, `"Chief Executive Officer"`)
- `is_officer: bool`
- `is_director: bool`
- `is_ten_pct_owner: bool`
- `transaction_date: str`
- `transaction_code: str` (`P`, `S`, `F`, `M`, `G`, etc.)
- `acquired_disposed: str` (`A` for acquired, `D` for disposed)
- `shares: float`
- `price: float | None`
- `remaining_shares: float | None`
- `is_10b5_1: bool` (Rule 10b5-1 pre-scheduled trading plan flag)
- `footnotes: list[str]`

### `Form4AuditSummary`
- `ticker: str`
- `filing_date: str`
- `net_discretionary_shares: float` ($\sum P - \sum S$)
- `open_market_sales_shares: float` ($\sum S$)
- `open_market_buys_shares: float` ($\sum P$)
- `tax_withholding_shares: float` ($\sum F$)
- `option_exercises_shares: float` ($\sum M$)
- `rule_10b5_1_active: bool`
- `transactions: list[Form4Transaction]`

### Functions
- `parse_form4_xml(xml_content: str) -> Form4AuditSummary`:
  Parses raw XML string using Python standard library `xml.etree.ElementTree`.

## Donor Code Provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.sec.form4.parse_form4_xml` | adapted | `reference/edgartools/edgar/ownership/forms.py:50-120` | Implemented via pure Python stdlib `xml.etree.ElementTree` to guarantee zero dependency failures and exact arithmetic isolation of Code F tax withholding. |
