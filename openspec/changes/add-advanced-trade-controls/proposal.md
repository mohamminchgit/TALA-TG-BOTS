# Change: Align trading policy, cancellation flow, and admin controls

## Why
Current trading behaviour lacks the fixed spread policy requested by operations, the bots cancel speculative orders by replying to their own raw text instead of the supervisor message, and there is no operator console to tune limits or pause the engine safely. Automatic advertisements also trigger trades that the business now considers too risky.

## What Changes
- Enforce a configurable fixed-delta spread policy: seek profitable counterparties first, otherwise place bridging orders using the delta, and respect a configurable carry-over quantity cap.
- Track supervisor reformatted messages so auto cancellations reply with `ن` to the correct post, with the timeout configurable at runtime.
- Treat auto-advertisement messages as monitored opportunities only—never post into the market unless a qualifying counterparty exists—and respect per-opportunity carry limits.
- Introduce a dedicated inline-keyboard admin bot for live tuning (engine pause/resume, quantity caps, opportunity thresholds, auto-`ن` delay, status insight) without loading the trading engine.

## Impact
- Affected specs: `trade-engine`, `telegram-agent`, `admin-control-bot`
- Affected code: `src/engine/core/*` (matcher, predictive logic, state tracking), `src/bot_agent/*` (command executor, monitors), configuration loaders, Redis/state persistence, new Bot API service under `src/admin_bot/`
