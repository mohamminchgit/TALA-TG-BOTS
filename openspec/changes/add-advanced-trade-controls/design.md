## Context
The trading engine must pivot to a fixed-spread policy with configurable carry limits while continuing to respect supervisor expectations. The change also introduces a dedicated Bot API admin surface that must not block engine throughput. Existing predictive and immediate strategies require extensions to locate counterparties before posting bridging orders, and cancellation has to target the supervisor-issued message IDs rather than the raw agent text.

## Goals / Non-Goals
- Goals:
  - Enforce a single configurable spread delta across buy-first and sell-first flows.
  - Persist supervisor reformatted message metadata to drive accurate cancellations and analytics.
  - Keep auto-advertisement inventory in memory for opportunistic fills without auto-posting.
  - Provide an inline-keyboard admin bot that updates engine settings safely and reports status.
- Non-Goals:
  - Building full analytics dashboards (only lightweight telemetry exposed via admin bot).
  - Replacing existing CLI admin commands (they remain supported alongside the new bot).
  - Implementing historical backfill of supervisor message IDs (only track from deployment onward).

## Decisions
- Use a shared `TradePolicyService` to calculate target prices, carry limits, and opportunity eligibility so both matcher and predictive paths reuse the same policy logic.
- Extend order-tracking structures to store supervisor message IDs (IDs emitted post confirmation) alongside bot-authored IDs, enabling correct `ن` replies.
- Tag auto-advertisement messages (`آگهی خودکار`) at classification time and store them in a dedicated cache that the policy service consults before spawning opportunities.
- Host the admin bot as a lightweight asyncio task that consumes Redis commands, backed by Bot API inline keyboards for quick toggles; persist configuration updates in SQLite `config` table for durability.
- Introduce configuration keys (`FIXED_SPREAD_DELTA`, `BASE_CARRY_LIMIT`, `OPPORTUNITY_CARRY_LIMIT`, `AUTO_N_DELAY_SECONDS`) with overrides accepted via admin bot commands.

## Risks / Trade-offs
- Centralising policy decisions can increase coupling; mitigate by providing pure functions that accept snapshot data to keep engine components testable.
- Tracking supervisor IDs depends on timely classification of supervisor messages; if supervisors change format, cancellation may fail. Mitigate with regex fallback and metrics exposed in admin bot.
- Admin bot introduces new external dependency (Bot API token). If unavailable, operators must fall back to CLI; provide health indicator in logs when bot disconnects.
- Inline keyboards can become cluttered as options grow; focus on the five requested controls and collapse secondary metrics into a single status panel to preserve usability.

## Migration Plan
1. Deploy policy service and metadata persistence without flipping new behaviour (feature flags default to current posture where possible).
2. Enable fixed delta and carry limits through configuration once countersigned by operations.
3. Roll out admin bot with limited operator access, verifying pause/resume logic in staging.
4. Enable auto-advertisement monitoring mode and observe for one trading session before enforcing.

## Open Questions
- Do auto-advertisement messages always begin with the literal `آگهی خودکار`, or are there alternate prefixes that should be included?
- Should the admin bot apply granular permissions per operator, or will Telegram group membership suffice?
- What is the expected persistence horizon for cached auto-advertisements (e.g., clear after fill, timeout after N minutes)?
