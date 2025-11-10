# Operations Runbook

This runbook provides day-to-day operating guidance for the Telegram arbitrage bot stack.

## 1. System Overview
- **Components**: Telegram agents (`python main.py run`), Engine (`python main.py engine`), Redis (pub/sub + key/value), SQLite (`data/database.db`), optional admin scripts in `scripts/`.
- **Critical Channels**: `group_events`, `execution_commands`, `execution_results`, `admin_commands`, `admin_reports`.
- **Primary Data Stores**: Redis for transient state (`executed_trades_cache`, `predictive:trade:*`, engine gates) and SQLite for durable history (`trade_history`, `config`, `performance_stats`, `alert_log`).
- **KPIs**: Command success rate, confirmation latency, speculative fill ratio, flood-wait frequency, `admin_reports` noise.

## 2. Routine Operations
1. **Daily Pre-Flight**
   - Ensure Redis reachable: `redis-cli PING`.
   - Check database integrity: `sqlite3 data/database.db "PRAGMA integrity_check;"` (expect `ok`).
  - Verify required env vars (`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `REDIS_URL`) plus predictive tunables (`PREDICTIVE_PRICE_DELTA`, `PREDICTIVE_SUFFIX_DIGITS`) present in `.env`.
   - Smoke test scripts: `python scripts/simulate_arbitrage.py --dry-run` (use `--help` to discover flags if added later).
2. **Service Launch**
   - Start engine: `python main.py engine` (ideally inside a supervisor/service wrapper).
   - Start agents in separate session: `python main.py run`.
   - Confirm subscriptions: `python main.py listen --channel admin_reports` to ensure activity.
3. **Operational Logging**
   - Logs print to stdout; capture using PowerShell transcript or `Start-Transcript` when running long sessions.
   - Forward key events by tailing `admin_reports` and storing snapshots in `logs/` (manual copy).
4. **Health Probes**
   - Redis queue depth: `redis-cli LLEN engine:pending` (if list keys configured) or `KEYS predictive:trade:*` to monitor stranding.
   - Engine heartbeat: watch for `engine_ready` message in `admin_reports` within 5 seconds of start.

## 3. Dependency Management
- **Redis**
  - Default URL `redis://localhost:6379/0`; tune `REDIS_URL` in `.env` if switching hosts.
  - Backup by snapshotting Redis dump (`redis-cli SAVE`). Clear straggler predictive keys via `redis-cli KEYS 'predictive:*' | foreach { redis-cli DEL $_ }` (PowerShell pipeline).
- **SQLite**
  - File lives in `data/database.db`. Back up by copying file while services stopped: `Copy-Item data\database.db data\archive\database-$(Get-Date -Format yyyyMMdd-HHmmss).db`.
  - For growth >1 GB consider migrating to PostgreSQL before go-live; update `DatabaseManager` accordingly.
- **Telegram Sessions**
  - Refresh session files via `scripts/generate_session.py` when credentials rotate. Store outputs under `sessions/` with restricted permissions.

## 4. Incident Response Playbooks
### 4.1 Engine Crash
- **Detect**: Engine console stops emitting heartbeats; `admin_reports` silent.
- **Actions**:
  1. Collect logs (save transcript).
  2. Restart engine: `python main.py engine`.
  3. Confirm `engine_ready` and that `admin_reports` acknowledges restart.
  4. Check `predictive:*` keys and clear stale entries.
- **Postmortem**: File incident notes in `docs/incidents/<date>.md` (create directory if needed).

### 4.2 Redis Outage
- **Detect**: Publish/subscribe errors in logs, `ConnectionError` traces.
- **Actions**:
  1. Pause trading via admin command: `python scripts/send_admin_command.py '{"command":"monitor_only","enabled":true}'` (engine must be running to accept).
  2. Restart/repair Redis service. On Windows: `Restart-Service redis` or consult hosting provider.
  3. Flush inconsistent caches only if data corrupt (`redis-cli FLUSHDB`), otherwise retain state.
  4. Resume trading: `python scripts/send_admin_command.py '{"command":"monitor_only","enabled":false}'`.

### 4.3 Telegram Flood-Wait / Rate Limit
- **Detect**: Execution results include `status=flood_wait` with `details.wait_seconds`.
- **Actions**:
  1. Confirm risk manager triggered circuit breaker via `admin_reports`.
  2. Keep engine running; risk manager will auto-resume after delay.
  3. If manual intervention needed, issue `panic` with buffer: `python scripts/send_admin_command.py '{"command":"panic","duration_seconds":60}'`.
  4. After flood-wait period, issue `resume` and monitor `execution_commands` volume.

### 4.4 Database Corruption / Locked DB
- **Detect**: SQLite `OperationalError: database is locked` or failed integrity check.
- **Actions**:
  1. Stop engine and agents.
  2. Backup current db file for forensics.
  3. Restore last known good backup into `data/database.db`.
  4. Run integrity check and restart services.

### 4.5 Admin Bot Offline
- **Detect**: Commands return no response, `admin_reports` silent.
- **Actions**:
  1. Ensure `main.py run` process alive.
  2. Re-login with `scripts/generate_session.py` if session expired.
  3. Restart bot process; watch for `bot_ready` in logs.

## 5. Rate-Limit & Recovery Guidance
- Telegram flood waits shorter than 60s auto-managed; ensure `FLOOD_WAIT_GRACE_SECONDS` matches environment.
- For extended outages, keep `monitor_only` mode enabled and manually settle open trades using `publish_execution_result.py` to mark reconciliations.
- If risk layer triggers emergency exits repeatedly, lower `MAX_CONCURRENT_TRADES` in config via `update_config` admin command.

## 6. Data Lifecycle & Archival
- Rotate `trade_history` by exporting to CSV monthly: `sqlite3 data/database.db -csv "SELECT * FROM trade_history" > exports/trade_history-$(Get-Date -Format yyyyMMdd).csv`.
- Archive Redis snapshots (`dump.rdb`) alongside database exports for replay testing.
- Sanitise sensitive data before sharing outside core team.

## 7. Maintenance Windows
- Schedule downtime windows for major upgrades; send `panic` command 5 minutes prior to freeze trading.
- During window, stop agents then engine. Apply patches, run migrations, then restart services in engine-first order.

## 8. Observability
- Enable verbose logging via `set LOG_LEVEL=DEBUG` (PowerShell: `$env:LOG_LEVEL="DEBUG"`).
- For external monitoring, tail outputs into files (e.g., `python main.py engine | Tee-Object -FilePath logs/engine-$(Get-Date -Format yyyyMMdd).log`).
- Use `admin_reports` channel as primary alert feed; consider wiring into Telegram admin group or another notification pipeline.

## 9. Communication Protocol
- Classify incidents (P1 engine down, P2 degraded, P3 advisory).
- Notify stakeholders via Telegram admin group and email distribution on P1/P2 within 10 minutes.
- Record resolution summary in shared doc and update runbook if new steps discovered.

## 10. Checklist Summary
- [ ] Daily health checks complete
- [ ] Redis operational & cleared of stale predictive keys
- [ ] SQLite integrity verified and backup recent
- [ ] Engine + agents running with heartbeats
- [ ] Admin commands responsive
- [ ] Incident log updated for any anomalies
