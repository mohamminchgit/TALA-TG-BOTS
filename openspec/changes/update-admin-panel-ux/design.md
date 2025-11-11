## Context
The current admin bot renders an English dashboard, posts confirmation messages for every button tap, and uses separate buttons for engine stop/start. Operators requested a Persian-first control panel that mirrors the engine state exactly, offers inline guidance, and keeps the chat clean. Additionally, cancellation acknowledgements (`ن`) currently reply to the bot’s own post instead of the supervisor confirmation, so human moderators do not see the cancellation in the right place.

## Goals / Non-Goals
- Goals: deliver a Persian dashboard with reorganised controls, introduce `/help` and reset-to-default flows, rely on engine-confirmed values for UI refresh, and ensure cancellation acks address the supervisor message id.
- Non-Goals: redesigning the Redis command schema, changing trading algorithms, or overhauling deployment scripts.

## Decisions
- Decision: Capture the initial policy snapshot and engine config dictionary on admin bot startup so we can issue a reset command that replays those default values back through the engine, ensuring a single source of truth.
- Decision: Build a Persian dashboard renderer that formats the requested headline (engine status), aggregated stats (profit, trade counts, open positions), and configuration values using RTL-friendly text while keeping numeric values in familiar digits.
- Decision: Swap the dual start/stop buttons for one toggle that inspects the latest `monitor_only`/`trading_allowed` flags to decide the label (`🔴 خاموش کردن موتور` vs `🟢 روشن کردن موتور`).
- Decision: Replace chat notifications with `event.answer(..., alert=True)` so updates surface as modal alerts, while the dashboard refresh waits for the engine’s `config_updated` payload before mutating local state.
- Decision: Extend `AdminCommandService._current_state_snapshot()` with live open-trade counts (from `TradeTracker` and pending predictive trades) and surface those in the Persian dashboard so operators see real-time exposure.
- Decision: Enrich `cancel_own_order` commands with a `reply_to_message_id` resolved from `TradeTracker` or the order book so agents reply `ن` to the supervisor confirmation before deleting the speculative message.

## Risks / Trade-offs
- Translating strings into Persian may require consistent localisation utilities; mixing English digits with Persian prose could confuse some users. Mitigation: retain numeric digits as Western numerals while providing contextual Persian labels.
- Relying on engine-acknowledged updates introduces latency between button tap and UI refresh. Mitigation: keep inline alerts responsive and show a short-lived “در حال به‌روزرسانی...” state if needed.
- Reset-to-default must not overwrite production-tuned values unintentionally. Mitigation: gate the action behind a confirmation alert and rely on the persisted defaults captured at boot.

## Migration Plan
1. Implement the new Persian renderer, keyboard layout, and toggle behaviour in the admin bot, using a stored baseline snapshot.
2. Extend engine services to supply enriched status snapshots, honour the reset command, and include supervisor message ids when issuing cancellation commands.
3. Update Telegram agents to consume the enriched cancellation metadata and reply `ن` to the supervisor confirmation.
4. Manual verification in a staging chat to confirm layout, alerts, reset flow, and correct cancellation behaviour.

## Open Questions
- Should numeric values (prices, spreads) also render using Persian digits? (Currently assumed to remain English for clarity.)
- Do we need a rate limit on `/help` to avoid spam, or is occasional use acceptable?
