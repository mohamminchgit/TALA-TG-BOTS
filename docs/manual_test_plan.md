# Manual Test Plan

This plan outlines end-to-end validation steps for each roadmap stage. All tests assume the project is configured per `README` and that Redis and SQLite are accessible from the test machine.

## Prerequisites
- Python 3.10+
- Redis server reachable at `REDIS_URL`
- `.env` populated with Telegram credentials (or mocked when using simulation scripts)
- Virtual environment activated with project dependencies installed
- Ensure `python main.py run` and `python main.py engine` are not already running before starting each test suite

## Stage 1 – Foundation & Infrastructure
1. **Configuration Loader**
   - Run `python - <<"PY"\nfrom src.config.settings import get_settings\nprint(get_settings())\nPY`.
   - Expect an object dump without exceptions and paths resolved.
2. **Database Schema**
   - Execute `python - <<"PY"\nfrom src.common.db import DatabaseManager\nfrom pathlib import Path\nDatabaseManager(Path("data/database.db")).initialize_schema()\nprint("schema ok")\nPY`.
   - Verify `data/database.db` exists and `sqlite3 data/database.db ".tables"` lists `config`, `trade_history`, `performance_stats`, `alert_log`.
3. **Redis Connectivity**
   - Run `python - <<"PY"\nimport asyncio\nfrom src.common.redis import RedisManager, RedisChannels\nasync def ping():\n    manager = RedisManager("redis://localhost:6379/0", RedisChannels("group_events","execution_commands","execution_results","admin_commands","admin_reports"))\n    await manager.publish("group_events", "ping-test")\nasyncio.run(ping())\nPY` adjusting URL as needed.
   - Confirm no connection errors.

## Stage 2 – Telegram Agent Layer
1. Start agents: `python main.py run` (leave running).
2. In a second shell, tail execution results: `python main.py listen --channel execution_results`.
3. From a test account, post sample buy/sell/escape messages in source and destination groups; verify logs show normalized payloads.
4. Inject command via script: `python test_command.py`.
   - Confirm Telegram group receives the order, and `execution_results` prints a success entry.
5. Stop the agents with `Ctrl+C` once tests pass.
6. Review the source group history to ensure the bot does not emit acknowledgement chatter (no `received ... ✅` messages); rely on Redis logs for confirmation instead.

## Stage 3 – Arbitrage Engine Core
1. Start engine only: `set LOG_LEVEL=DEBUG & python main.py engine`.
2. Launch simulator: `python scripts/simulate_arbitrage.py`.
   - Expect execution commands for source/destination, success results, and new rows in `trade_history` (`sqlite3 data/database.db "SELECT trade_id,status,strategy FROM trade_history ORDER BY id DESC LIMIT 2;"`).
3. Inspect Redis executed cache: `redis-cli SMEMBERS executed_trades_cache` (or equivalent). IDs from the simulation should be present.
4. Verify `LOG_LEVEL=DEBUG` output shows order book reconciliation summaries.
5. **Multi-Counterparty Aggregation**
   - Manually post two destination buy orders at the same or better price than the current source sell (e.g., `🔵 علی 1 خ 45310`, `🔵 حسین 2 خ 45310`).
   - Post a single source sell for quantity 3 at price 45300.
   - Confirm the engine issues two destination reply commands (1 and 2 units respectively) before a single aggregated source reply for quantity 3, and that `execution_results` reports a single trade ID with multiple destination legs.
6. **Order Book Hygiene**
   - Delete one of the destination orders directly in Telegram (or send a bare `ن` reply) and ensure the deleted order disappears from the status output (`python scripts/send_admin_command.py '{"command":"status"}'`). The engine should log "Removed ... due to message deletion".

## Stage 4 – Predictive Market-Making
1. With engine running, publish a single source sell event without a matching destination order:
   - Use `redis-cli` or a helper script to send a manual source sell payload (see `scripts/simulate_arbitrage.py` for format).
2. Observe engine logs for a predictive trade ID (`pred-*`) and confirm a `post_new_order` command is emitted for the destination bot.
3. In the destination group, confirm the speculative post appears in trader format using the configured suffix digits. With default settings, expect four digits padded with zeros (e.g., `1ف0310` if price is 45310). Repeat after changing `PREDICTIVE_SUFFIX_DIGITS=3` and `PREDICTIVE_PRICE_DELTA=25` in `.env`, restarting the engine, and verify the suffix length and delta adjust accordingly.
4. Publish a mock confirmation for the speculative order using `python scripts/publish_execution_result.py` with payload `{ "trade_id": "pred-...", "agent": "destination", "status": "confirmation_detected" }`.
5. Confirm the engine issues a follow-up reply command to the source group and that the predictive trade is recorded in `trade_history` with strategy `predictive`.
6. Trigger a speculative timeout and verify the cancellation command causes the destination bot to reply `ن` before deleting its message (inspect Telegram history and `execution_results`).

## Stage 5 – Risk Management & Failure Handling
### 5.1 Layered Exit Strategy
1. Run engine and agents. Trigger a trade where only the source leg succeeds:
   - Emit execution result: `python scripts/publish_execution_result.py '{"trade_id":"test-risk-1","agent":"source","status":"success"}'`.
   - After 2 seconds emit a timeout for destination: `python scripts/publish_execution_result.py '{"trade_id":"test-risk-1","agent":"destination","status":"confirmation_timeout"}'`.
2. Monitor `execution_commands` for break-even order issuance, followed by stop-loss and emergency commands if confirmations are not reported.
3. Verify `admin_reports` channel logs `exit_started`, `exit_complete`, and potentially `circuit_breaker` events.

### 5.2 Speculative Timeout Handling
1. Trigger a predictive trade (Stage 4 steps) and refrain from sending a fill.
2. Wait for `SPECULATIVE_TRADE_TIMEOUT_SECONDS` to elapse; confirm the engine issues a `cancel_own_order` command and cleans up Redis keys `predictive:trade:*`.

### 5.3 FloodWait Crisis Protocol
1. Publish a flood wait result: `python scripts/publish_execution_result.py '{"trade_id":"risk-flood","agent":"destination","status":"flood_wait","details":{"wait_seconds":25}}'`.
2. Check `admin_reports` for a flood wait notification and verify that trading pauses (`ImmediateArbitrageMatcher` logs no new attempts while pause window is active).
3. After the delay, ensure the risk manager commands an emergency exit and a circuit-breaker pause is applied.

## Stage 6 – Management Panel & Observability
1. With engine running, send admin commands using `python scripts/send_admin_command.py`:
   - Update config: `'{"command":"update_config","updates":{"minimum_profit_spread":5}}'` and observe confirmation on `admin_reports`.
   - Toggle monitor-only mode: `'{"command":"monitor_only","enabled":true}'`; confirm engine stops matching trades.
   - Panic/resume: `'{"command":"panic","duration_seconds":15}'` then `'{"command":"resume"}'`; ensure pause/resume messages are logged.
   - Status: `'{"command":"status"}'` to review order book summary.
2. Validate shutdown: `'{"command":"shutdown"}'` and ensure engine tasks exit gracefully.

## Stage 7 – Validation & Operations
- Execute the operational runbook (`docs/operations_runbook.md`) and deployment playbook (`docs/deployment_playbook.md`) steps in a staging environment prior to production rollout.
- Record outcomes, log timestamps, and attach screenshots or terminal outputs where relevant for archival.

## Test Completion Criteria
- All stages complete without unhandled exceptions.
- Redis caches and SQLite tables reflect expected state changes.
- Admin reports capture every critical event (exits, pauses, updates).
- Scripts return zero exit codes; logs show intended behavior at each phase.

## Post-Test Checklist
- Stop all running scripts with `Ctrl+C`.
- Clear temporary Redis keys: `redis-cli KEYS 'predictive:*' | xargs redis-cli DEL` (use with caution).
- Archive `data/database.db` and relevant log files in the deployment package.
