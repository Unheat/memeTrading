# Module Spec — Institutional Fusion Engine

## Goal

Produce a fail-closed, evidence-backed research workflow which preserves existing local SEC, market, article, and RAG collection. Deterministic accounting and valuation outputs precede independent thesis generation. A missing source field produces an explicit unavailable status; it never produces a substituted estimate.

## Requirements and acceptance criteria

1. `app/valuation/calculator.mjs` is the adapted deterministic calculator; it accepts a JSON model on its existing command line and emits JSON only on success.
2. `app/valuation/engine.py` invokes Node with a temporary JSON file, has a bounded timeout, validates the result is a JSON object, and reports structured errors without claiming process-performance characteristics.
3. Specialist nodes produce separate reports: forensic, thematic, sector, moat, and quant. Thematic is LLM-generated but constrained to cited evidence; the others are deterministic where possible.
4. Phase 1 stores successful `get_sec_financials` payloads verbatim in `state.sec_financials`. Phase 2 forensic work uses those SEC period fields; Phase 3 derives FCF only when same-period CFO and CapEx exist, shares only from market `shares_outstanding`, and net cash only from SEC cash/debt. Missing prerequisites explicitly remain unavailable.
5. DCF uses only source-backed inputs plus named baseline constants. Constants and source-field mapping are carried in the quant model/report; LLM outputs cannot populate a calculator input.
6. Gates run in order: G1 collection evidence, G2 accounting, G3 valuation reproducibility, G4 source-backed risk/reward. Every failing G2/G3/G4 gate reaches a deterministic `VALIDATION_WATCH`/`NO_POSITION` finalizer and committee-style zero-allocation outcome; it must not terminate with missing outcome data. Accounting absence cannot create a short approval.
7. Bull and bear are deliberately sequential due to shared LangGraph update semantics. Both consume sealed Phase 1–3 facts and bear receives no bull report; graph makes no parallelism claim.
8. The committee can approve only when a source-backed price, a reproducible quant base/low valuation, a valid trade-risk stop rationale, and G4 all pass. It must not replace a bear floor with an arbitrary percentage stop.
9. The memo always renders eight sections and only renders source-backed/deterministic report values. Failed gates override raw model final text. Media generation is blocked if citation validation fails.
10. Focused tests cover wrapper errors, SEC payload mapping, no-data outcome, no-fabrication behavior, gate outcomes, valuation provenance, independent debate inputs, and orchestration.

## Constraints and dependency boundary

- Node.js is invoked as a black-box executable with `subprocess.run`; no timing guarantee is made.
- Existing LangGraph/LangChain APIs remain black-box dependencies.
- Calculator models use only normalized values delivered by existing local sources. `calculator.mjs` does not acquire data.
- The donor's YAML contracts are intentionally not used because this application has its own TypedDict/dataclass state contracts.

## Donor code provenance

| Local symbol | Reuse type | Exact donor location | Deliberate changes |
| --- | --- | --- | --- |
| `app.valuation.calculator.round` | copied | `reference/investment-research/pipeline/calculator.mjs:28-31`, `round` | None; retained deterministic rounding behavior. |
| `app.valuation.calculator.dcf` | copied | `reference/investment-research/pipeline/calculator.mjs:36-78`, `dcf` | None. |
| `app.valuation.calculator.solveReverseDCF` | copied | `reference/investment-research/pipeline/calculator.mjs:84-201`, `solveReverseDCF` | None. |
| `app.valuation.calculator.computeBeneishMScore` | copied | `reference/investment-research/pipeline/calculator.mjs:244-276`, `computeBeneishMScore` | None. |
| `app.valuation.calculator.computeSloanAccrual` | copied | `reference/investment-research/pipeline/calculator.mjs:282-298`, `computeSloanAccrual` | None. |
| `app.valuation.calculator.compute` | copied | `reference/investment-research/pipeline/calculator.mjs:576-738`, `compute` | None; caller restricts supplied input values. |
| `app.valuation.calculator.verify` | copied | `reference/investment-research/pipeline/calculator.mjs:743-758`, `verify` | None. |
| `app.valuation.calculator.runCli` | copied | `reference/investment-research/pipeline/calculator.mjs:763-824`, `runCli` | None. |
| `app.agent.expectations.run_expectations_analyst` | adapted | `reference/investment-research/prompts/valuation-modeler.prompt.md:1-30` and `contracts/valuation-modeler.yaml:1-35` | Dynamic expectation gap and DCF assumption generation; Reverse DCF solver executed via calculator.mjs. |
| `app.agent.specialists.run_forensic_analysis` | adapted | `reference/investment-research/prompts/forensic-accounting.prompt.md:1-45` and `contracts/forensic-accounting.yaml:1-32` | Evaluates Beneish M-Score, Sloan accrual, SBC dilution walk, and balance sheet debt covenants via LLM. |
| `app.agent.specialists.run_sector_analysis` | adapted | `reference/investment-research/prompts/sector-specialist.prompt.md:1-23` and `contracts/sector-specialist.yaml:1-34` | Analyzes unit economics, customer concentration, and industry dynamics via LLM. |
| `app.agent.specialists.run_moat_analysis` | adapted | `reference/investment-research/prompts/sector-specialist.prompt.md:1-23` and `schemas/sector-deep-dive.schema.json:1-45` | Analyzes competitive moat durability, switching costs, and network effects via LLM. |
| `app.agent.specialists.run_thematic_analysis` | adapted | `reference/investment-research/prompts/macro-thematic.prompt.md:1-55` and `contracts/macro-thematic.yaml:1-33` | Analyzes multi-year capex waves, physical bottlenecks, and value-chain rents via LLM. |
| `app.agent.committee.run_investment_committee` | adapted | `reference/investment-research/prompts/cio-ic.prompt.md:1-34` and `contracts/cio-ic.yaml:1-38` | CIO LLM deliberates on Bull vs Bear debate, passing discipline, and assigns conviction tier and Kelly position sizing. |

All other calculator exports are copied as supporting implementation from `reference/investment-research/pipeline/calculator.mjs` and retain their donor behavior. `engine.py` and the specialist nodes are locally written; no donor production code is adapted there.
