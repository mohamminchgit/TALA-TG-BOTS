## 1. Specification
- [x] 1.1 Extend `project-roadmap` requirements to cover four-digit speculative pricing and configurable differential.
- [x] 1.2 Document volume aggregation, stale-order eviction, and cancellation rules in the spec delta.
- [x] 1.3 Capture predictive follow-through guarantees and cancellation reply semantics in the spec.

## 2. Implementation
- [x] 2.1 Add configuration entries for predictive suffix digit count and delta (default 10) with documentation.
- [x] 2.2 Update predictive market maker to compute price deltas using config, emit four-digit trader text, and immediately trigger the source leg after fill regardless of alias overlap.
- [x] 2.3 Enhance opportunity evaluation to aggregate counterparties, splitting volumes across best-priced orders before issuing commands.
- [x] 2.4 Improve order book maintenance to purge on `ن` messages, message deletions, and missing supervisor confirmations; ensure bot cancellations reply "ن" to supervisor messages when available.
- [x] 2.5 Adjust command executor and risk manager flows to use the new cancellation behaviour and handle missing reply targets gracefully.
- [x] 2.6 Update manual test plan / scripts to validate multi-counterparty fills, four-digit pricing, and stale-order eviction.

## 3. Validation
- [x] 3.1 Run staging simulations covering split fills, cancellation events, and predictive closures; capture logs proving source leg execution.
- [x] 3.2 Document validation output in `docs/validation_reports/` with screenshots/log hashes.
