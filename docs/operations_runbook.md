# Operations Runbook

This runbook provides day-to-day operating guidance for the Telegram arbitrage bot stack.

## 1. System Overview
- **Components**: Telegram agents (`python main.py agent --name source|destination`), Engine (`python main.py engine`), Admin bot (`python main.py admin`), Redis Streams, PostgreSQL, all orchestrated via Docker Compose (`deployment/docker-compose.yml`).
- **Critical Streams**: `group_events`, `execution_commands`, `execution_results`, `admin_commands`, `admin_reports`.
- **Primary Data Stores**: Redis Streams for real-time messaging; PostgreSQL (`telethon_sessions`, `trade_history`, `config`, `performance_stats`, `alert_log`) for durable state and session storage.
- **KPIs**: Command success rate, confirmation latency, speculative fill ratio, flood-wait frequency, session health (stale/missing sessions).

## 2. Routine Operations
1. **Daily Pre-Flight**
   - Ensure Docker services healthy: `docker compose -f deployment/docker-compose.yml ps` — all services should be `Up`.
   - Confirm Redis reachable: `redis-cli -h localhost -p ${REDIS_PORT:-6379} PING` (expect `PONG`).
   - Confirm PostgreSQL accessible: `psql "${DATABASE_URL}" -c "SELECT NOW();"`.
   - Verify required env vars (`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `DATABASE_URL`, `REDIS_URL`) plus predictive tunables (`PREDICTIVE_PRICE_DELTA`, `PREDICTIVE_SUFFIX_DIGITS`) present in `.env`.
   - Smoke test workflow: `python scripts/simulate_arbitrage.py --dry-run`.
2. **Service Launch**
   - Preferred: `docker compose -f deployment/docker-compose.yml up -d` (engine, agents, admin bot, Redis, Postgres).
   - Manual mode (for debugging): start engine `python main.py engine`, agents `python main.py agent --name source|destination`, admin bot `python main.py admin`.
   - Confirm subscriptions: `python main.py listen --channel admin_reports` to ensure activity.
3. **Operational Logging**
   - Logs print to stdout; capture using PowerShell transcript or `Start-Transcript` when running long sessions.
   - Forward key events by tailing `admin_reports` and storing snapshots in `logs/` (manual copy).
4. **Health Probes**
   - Redis queue depth: `redis-cli LLEN engine:pending` (if list keys configured) or `KEYS predictive:trade:*` to monitor stranding.
   - Engine heartbeat: watch for `engine_ready` message in `admin_reports` within 5 seconds of start.

## 3. Dependency Management
- **Redis**
  - Default URL `redis://localhost:6379/0`; adjust `REDIS_URL` in `.env` if switching hosts or databases.
  - Data persistence handled via Docker volume `redis-data`. Snapshot with `redis-cli SAVE` if manual backup needed.
- **PostgreSQL**
  - Connection string defaults to `postgresql://talatg:talatg@localhost:5432/talatg`; override `DATABASE_URL` in `.env` for production.
  - Back up using `pg_dump "${DATABASE_URL}" > backups/talatg-$(date +%Y%m%d).sql` (ensure directory exists).
  - Use `psql "${DATABASE_URL}" -c "\dt"` to confirm schema loaded.
- **Telegram Sessions**
  - Sessions live in `telethon_sessions` (Postgres). Use `python main.py ensure-sessions` before deployments, or admin bot “🔐 سشن …” buttons to re-authorise.

### 3.1 Session Onboarding Workflow
1. Run `python main.py ensure-sessions` (locally or over SSH) before any deployment. The command pauses, sends login codes per bot, and resumes after sessions persist.
2. During deployment, `deployment/deploy.ps1` automatically:
   - Pulls Docker images.
   - Starts Postgres/Redis containers.
   - Invokes `python3 main.py ensure-sessions` on the remote host (interactive prompts appear in the initiating terminal).
3. In emergencies, the admin bot dashboard exposes “🔐 سشن …” buttons. Pressing a button:
   - Sends the login code to the specified phone number.
   - Prompts the operator to reply with `/code <bot> <code>` and, when needed, `/password <bot> <pass>`.
   - Updates session health indicators in the dashboard once complete.

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

### 4.4 Database Issues
- **Detect**: PostgreSQL connection failures, migration errors, or inconsistent telemetry.
- **Actions**:
  1. Stop engine and agents (`docker compose down` or individual stops).
  2. Capture backup: `pg_dump "${DATABASE_URL}" > backups/talatg-incident.sql`.
  3. Inspect logs via `docker compose logs postgres` for clues.
  4. Restore from backup if data corruption confirmed, rerun `python main.py ensure-sessions` afterwards to repopulate sessions.

### 4.5 Admin Bot Offline
- **Detect**: Commands return no response, `admin_reports` silent.
- **Actions**:
  1. Ensure admin container running: `docker compose ps admin-bot`.
  2. Use admin dashboard “🔐 سشن …” button to refresh missing sessions (provides `/code` prompt).
  3. Restart bot service: `docker compose restart admin-bot` (after session confirmed).
  4. Watch for `bot_ready` in logs.

## 5. Rate-Limit & Recovery Guidance
- Telegram flood waits shorter than 60s auto-managed; ensure `FLOOD_WAIT_GRACE_SECONDS` matches environment.
- For extended outages, keep `monitor_only` mode enabled and manually settle open trades using `publish_execution_result.py` to mark reconciliations.
- If risk layer triggers emergency exits repeatedly, lower `MAX_CONCURRENT_TRADES` in config via `update_config` admin command.

## 6. Data Lifecycle & Archival
- Export `trade_history` monthly: `psql "${DATABASE_URL}" -c "\COPY trade_history TO 'exports/trade_history-$(date +%Y%m%d).csv' CSV HEADER"`.
- Archive Redis snapshots (`dump.rdb`) and Postgres dumps together for replay testing.
- Sanitise sensitive data before sharing outside core team (remove phone numbers, session metadata).

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
