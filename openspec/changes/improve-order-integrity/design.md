## Context
Operational trials exposed multiple failure points: speculative trades can stall before closing the original source order, price suffixes shorter than four digits confuse the human supervisor, Redis retains cancelled orders causing phantom opportunities, and bot cancellations delete the bot’s own post rather than replying "ن" to the supervisor message. Volume handling also ignores multiple counterparties at the same price. These deficiencies must be resolved without reworking the entire engine.

## Goals / Non-Goals
- Goals: tighten predictive lifecycle, enforce trader-format pricing with configurable deltas, ensure volume aggregation across counterparties, purge stale order book entries, and fix cancellation semantics.
- Non-Goals: change rate-limit handling, redesign admin panel, or modify Telegram session management.

## Decisions
- **Four-digit suffix & delta**: Introduce config (`PREDICTIVE_PRICE_DELTA`, `PREDICTIVE_SUFFIX_DIGITS`) so speculative text encodes last `n` digits of the calculated price, zero-padded, preventing ambiguity.
- **Predictive follow-through**: Register source context before publishing speculative commands and trigger the source reply immediately after detecting a destination fill, even if the buyer alias matches the source alias.
- **Volume aggregation**: Extend the matcher/market maker to gather multiple counterparties ordered by best price, issuing sequential commands that cover the profitable quantity before mirroring to the other group.
- **Stale order eviction**: Listen for cancellation keywords (`ن`), message deletions, and missing supervisor confirmations to remove entries from the in-memory order book and Redis caches.
- **Cancellation reply**: When cancelling our own order, prefer replying with "ن" to the supervisor message id; if unavailable, accept silent fallback with logging.

## Risks / Trade-offs
- More complex aggregation increases command volume; mitigated by batching and respecting rate limits.
- Aggressive stale eviction may drop valid orders if parsing fails; hedge with careful normalization and debug logging.

## Open Questions
- None presently; requirements derived from user guidance and observed defects.
