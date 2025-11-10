## 1. Foundation & Infrastructure
- [x] 1.1 Scaffold `src/` directories and shared modules exactly as outlined in `openspec/project.md`
- [x] 1.2 Implement configuration loader and `.env` handling in `src/config/settings.py`
- [x] 1.3 Set up SQLite schema migrations for `config`, `trade_history`, `performance_stats`, and `alert_log`
- [x] 1.4 Implement Redis connection and Pub/Sub boilerplate shared between engine and bot agents

## 2. Telegram Agent Layer
- [x] 2.1 Create Telethon session generation script (`scripts/generate_session.py`) and document usage
- [x] 2.2 Build bot agent event handlers to normalize Persian/English inputs and publish to Redis `group_events`
- [x] 2.3 Implement command executor service to consume `execution_commands` and perform reply/post/cancel actions
- [x] 2.4 Add monitoring logic for confirmations with configurable timeout and structured logging

## 3. Arbitrage Engine Core
- [x] 3.1 Implement in-memory order book with reconciliation tasks driven by Redis events
- [x] 3.2 Add immediate arbitrage matcher that issues paired commands with shared `trade_id`
- [x] 3.3 Persist executed trades and cache message IDs to prevent duplicate processing

## 4. Predictive Market-Making Strategy
- [x] 4.1 Implement speculative order placement logic using `PREDICTIVE_SPREAD`
- [x] 4.2 Track pending speculative trades with TTL states in Redis
- [x] 4.3 Build completion flow that closes the source-side leg after destination fill

## 5. Risk Management & Failure Handling
- [x] 5.1 Implement layered exit strategy (Break-Even, Stop-Loss, Emergency Liquidation)
- [x] 5.2 Handle timeout and cancellation paths for speculative trades
- [x] 5.3 Add FloodWait crisis protocol with circuit breaker and delayed liquidation

## 6. Management Panel & Observability
- [x] 6.1 Implement Admin Bot command handlers for live configuration updates
- [x] 6.2 Deliver statistics and alert notifications via management group
- [x] 6.3 Support monitor-only mode, panic/resume controls, and safe shutdown handshake

## 7. Validation & Operations
- [x] 7.1 Provide end-to-end manual test plan per development stage
- [x] 7.2 Document operational runbooks covering dependencies, outage handling, and rate-limit recovery
- [x] 7.3 Prepare deployment/archival steps for OpenSpec once implementation completes
