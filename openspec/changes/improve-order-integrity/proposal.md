# Change: Improve Order Integrity And Supervisor Compliance

## Why
Live trading tests uncovered gaps that break the supervised workflow: predictive fills sometimes leave the source order untouched, speculative messages use ambiguous price suffixes, the engine evaluates opportunities against stale Redis entries, bot-issued cancellations delete the wrong message, and volume handling does not respect multiple counterparties. We must align autonomy with the trading supervisor’s expectations to avoid stuck positions and mispriced orders.

## What Changes
- Guarantee predictive trades always execute the original source order immediately after the speculative fill, even when aliases overlap.
- Standardise speculative text formatting to use four-digit price suffixes with configurable deltas so the supervisor can reformat unambiguously.
- Aggregate available counterparties so the engine buys or sells the total profitable quantity before mirroring the position in the opposite group.
- Harden the order book against stale data by reacting to `ن` cancellations, message deletions, and missing supervisor messages, and ensure bot cancellations reply to the supervisor post instead of deleting our own message.
- Update configuration, documentation, and monitoring hooks to cover the new behaviours and validations.

## Impact
- Affected specs: `project-roadmap`
- Affected code: `src/engine/core/predictive_market_maker.py`, `src/engine/services/order_book_service.py`, `src/engine/services/execution_result_service.py`, `src/bot_agent/services/command_executor.py`, `src/bot_agent/handlers/message_handler.py`, `src/engine/core/order_book.py`, `src/common/settings.py`, related tests/scripts.
