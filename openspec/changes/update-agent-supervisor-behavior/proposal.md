# Change: Align Agent Messaging With Trading Supervisor

## Why
Current bot behaviour breaks immersion in supervised trading groups: the source agent posts acknowledgement messages that reveal automation, and the predictive strategy posts fully formatted supervisor-style orders. This conflicts with real trading rooms where the human supervisor reformats raw trader texts, preventing us from deploying the system.

## What Changes
- Remove public acknowledgement posts from the source agent; group agents must operate silently except for actual trading actions.
- Adjust speculative order placement so the destination agent sends trader-style raw text (e.g. `1ف30`) and lets the human supervisor publish the formatted confirmation.
- Strengthen predictive pre-flight checks to ensure no viable counter-order already exists before posting a speculative message, avoiding unnecessary chatter.
- Update OpenSpec requirements and implementation tasks to capture these compliance rules.

## Impact
- Affected specs: `project-roadmap`
- Affected code: `src/bot_agent/handlers`, `src/bot_agent/services/command_executor.py`, `src/engine/core/predictive_market_maker.py`, `src/engine/core/order_book.py`, `src/engine/services/order_book_service.py`
