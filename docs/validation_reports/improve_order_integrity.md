# Improve Order Integrity Validation

## Summary
- Environment: Local staging (Redis 7.2, Python 3.10.13, Telethon 1.35)
- Config: `PREDICTIVE_PRICE_DELTA=15`, `PREDICTIVE_SUFFIX_DIGITS=4`, `MINIMUM_PROFIT_SPREAD=10`
- Focus Areas: Multi-counterparty aggregation, cancellation hygiene, predictive follow-through, stale order eviction
- Evidence: Redis transcripts (`logs/redis-improve-order-integrity.log`), execution_result snapshots (`logs/execution-results-2025-11-10.jsonl`), Telegram screenshots archived under `docs/validation_reports/artifacts/improve-order-integrity/`

## Test Matrix
| ID | Scenario | Steps | Outcome | Evidence |
| --- | --- | --- | --- | --- |
| V1 | Aggregated immediate trade spans multiple counterparties | Posted destination buys (1 @ 45310, 2 @ 45310), source sell 3 @ 45300 | Engine emitted two destination replies (`leg_index` 0/1) before single source reply; trade recorded once with quantity 3 | `execution-results-2025-11-10.jsonl` lines 12-19, engine log timestamp 19:32:11 |
| V2 | Destination cancellation replies `ن` prior to deletion | Triggered predictive timeout; inspected destination chat history | Bot replied `ن` to supervisor message before removing post; execution result flagged `already_deleted=false` | Screenshot `artifacts/destination-cancel.png`, Redis log line 221 |
| V3 | Stale order purged on message deletion | Deleted destination order message via Telegram client | Order book summary dropped message ID 8421; engine log showed "Removed 1 orders from destination due to message deletion" | `engine.log` timestamp 19:45:07, admin status payload #33 |
| V4 | Predictive suffix digits obey configuration | Set `PREDICTIVE_SUFFIX_DIGITS=3`, restarted engine, triggered predictive post | Destination message suffix zero-padded to 3 digits (`1ف310`), revert to 4 digits after reset | Screenshots `artifacts/predictive-suffix-3.png`, `artifacts/predictive-suffix-4.png` |
| V5 | Confirmation timeout escalates to risk exit | Injected `confirmation_timeout` for source leg, observed risk manager commands | Break-even order issued, followed by stop-loss and emergency after timers; admin reports captured lifecycle | `admin_reports.log` lines 77-102 |

## Observations
- Aggregated trades surface `leg_index` metadata allowing downstream auditing; ensure analytics pipeline reads `command.metadata` when segmenting fills.
- Cancellation acknowledgements rely on Telegram delivery; a missing reply target now logs warning but reports success with `already_deleted=true`.
- Message deletion events arrive batched; order book handler removes each ID individually, preventing phantom opportunities.

## Follow-ups
- Automate the split-fill simulation inside `scripts/simulate_arbitrage.py` to remove manual chat intervention.
- Extend analytics ETL to persist `legs` metadata alongside trade history records for richer reconciliation.
