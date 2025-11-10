# Validation Report – Agent Supervisor Compliance

| Check | Method | Result |
| --- | --- | --- |
| Source agent stays silent (no acknowledgement chatter) | Reviewed `src/bot_agent/handlers/message_handler.py` after test run; confirmations routed via Redis logs only. Manual Telegram staging check recommended before production. | PASS – Behaviour verified in code and during dry-run session (no extra replies observed). |
| Predictive posts use trader format (quantity+side+suffix) | Executed `PredictiveMarketMaker._format_price_suffix` via tooling to confirm `45430 -> 30`, `45520 -> 20`, `45303 -> 303`. | PASS – Trader-friendly suffix confirmed. |
| Predictive revalidation avoids redundant posts | Inspected logs while running `python scripts/simulate_arbitrage.py`; no speculative orders emitted when immediate counter-orders existed. | PASS – No redundant posts observed; log lines show "Skipping predictive ... due to new counter-order" when applicable. |

> Runbook: Repeat the above checks in staging with live Redis/Telegram before promotion. Capture screenshots of the destination group showing supervisor reformatted messages derived from raw bot posts.
