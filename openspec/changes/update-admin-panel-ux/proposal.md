# Change: Persian Admin Panel Experience and Engine State Sync

## Why
- The current admin dashboard surfaces English text and spams chat messages like `✅ Config updated`, which confuses Persian-speaking operators and clutters the control room.
- Critical controls such as engine power, help, and reset-to-default flows are fragmented or missing, making runtime operations error-prone for beginners.
- Cancellation acknowledgements (`ن`) reply to the wrong message id, so the trading supervisor leaves stale confirmations in place, violating the cancellation spec.
- The admin bot sometimes displays stale values after an update because it trusts its local state instead of the engine’s applied configuration snapshot.

## What Changes
- Translate the inline dashboard, notifications, and help content into Persian and restructure the message layout to highlight engine status, aggregated stats, and current settings exactly as operators requested.
- Replace per-click chat messages with inline alerts, reorganise the keyboard into the specified rows, and collapse engine on/off into a single context-aware toggle button.
- Add a `/help` command and a reset-to-defaults control that pushes the baseline configuration back into the engine and refreshes the dashboard.
- Ensure post-update dashboards use only the values echoed by the engine (not optimistic state), and extend the status snapshot with open-trade counts so displayed numbers always match live state.
- Fix the cancellation workflow so `cancel_own_order` commands include the supervisor confirmation message id, letting agents reply `ن` to the correct message before deleting the monitored post.

## Impact
- Affected specs: `admin-control-bot`, `trade-engine`, `telegram-agent`
- Affected code: `src/admin_bot/controller.py`, `src/admin_bot/__init__.py` (if present), `src/engine/services/admin_service.py`, `src/engine/core/predictive_market_maker.py`, `src/engine/services/risk_manager.py`, `src/engine/core/trade_tracker.py`, `src/bot_agent/services/command_executor.py`, and any shared localisation utilities.
