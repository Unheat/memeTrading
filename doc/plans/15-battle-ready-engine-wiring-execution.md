# Execution Plan 15 — Battle-Ready Engine Wiring

## Purpose

Address the four critical runtime gaps identified in the audit to make the forensic research engine battle-ready for real-money research:
1. Auto-initialize compliant SEC EDGAR identity (`app/sec/identity.py`).
2. Implement production embedding engine with deterministic fallback (`app/sec/embeddings.py`) and wire automatic corpus preparation and indexing into `pull_sec_filings`.
3. Provide default SEC assessor and wire `verify_sec_claim` in `app/agent/tools.py`.
4. Replace the placeholder `raise RuntimeError` in `app/sec/financials.py` with real `edgartools` XBRL statement extraction.
5. Build a deterministic Form 4 XML parser (`app/sec/form4.py`) that isolates Code `F` tax withholding from discretionary open-market selling.
6. Create an end-to-end smoke test verifying the whole pipeline without mocks.

## Donor Code Provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
|---|---|---|---|
| `app.sec.identity.ensure_sec_identity` | adapted | `reference/edgartools/edgar/settings.py:109-126`, `set_identity` | Automatically configures `EDGAR_IDENTITY` and calls `set_identity` with fallback default to prevent interactive prompts in headless runs. |
| `app.sec.financials._fetch_xbrl_statements` | adapted | `reference/edgartools/edgar/entity/core.py:1027-1071` & `edgar/financials.py` | Extracts quarterly statements from `Company.income_statement`, `balance_sheet`, `cash_flow_statement` with fallback to concept extraction. |
| `app.sec.form4.parse_form4_xml` | adapted | `reference/edgartools/edgar/ownership/forms.py:50-120` & Python `xml.etree.ElementTree` | Deterministic parsing of Form 4 XML extracting reporting owners, transaction codes (P, S, F, M), and Rule 10b5-1 trading plan flags. |

## Execution Sequence

1. Write module specs in `doc/specs/sec/`.
2. Implement and test `app/sec/identity.py` and `app/sec/embeddings.py`.
3. Auto-index downloaded filings in `app/sec/pull.py`.
4. Implement and test `app/sec/form4.py`.
5. Implement and test live XBRL statements extraction in `app/sec/financials.py`.
6. Wire `verify_sec_claim` in `app/agent/tools.py` with default embedder and assessor.
7. Add live smoke test and verify 185+ tests passing cleanly.
8. Commit to git.
