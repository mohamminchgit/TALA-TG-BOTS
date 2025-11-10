# Deployment Playbook

Use this playbook to promote the Telegram arbitrage bot to staging or production. Adjust paths for non-Windows hosts.

## 1. Scope & Roles
- **Release Owner**: Coordinates deployment, signs off.
- **Operator**: Executes commands on target host.
- **Observer**: Monitors Telegram channels/metrics during rollout.

## 2. Pre-Deployment Checklist
- [ ] Confirm proposal `add-project-roadmap` tasks 1–7 are marked complete in `openspec/changes/add-project-roadmap/tasks.md`.
- [ ] Git workspace clean; tags or branches labeled (`git status`, `git rev-parse HEAD`).
- [ ] `.env` updated with production credentials and reviewed for secrets hygiene.
- [ ] Predictive tunables reviewed: `PREDICTIVE_PRICE_DELTA` (absolute offset) and `PREDICTIVE_SUFFIX_DIGITS` (trader text length) set per roll-out expectations.
- [ ] Redis endpoint reachable from target host (`redis-cli -u $env:REDIS_URL PING`).
- [ ] Latest `trade_history` backup stored safely.
- [ ] Manual test plan executed in staging with PASS results documented in `docs/test-reports/<date>.md`.
- [ ] Operator has Telegram MFA devices handy in case sessions expire.

## 3. Packaging & Artifact Prep
1. Ensure dependencies up to date: `pip install -r requirements.txt` (inside virtualenv).
2. Run static checks/tests: `python -m compileall src` (basic syntax check) and any available unit tests.
3. Bundle source:
   ```powershell
   $timestamp = Get-Date -Format yyyyMMdd-HHmmss
   Compress-Archive -Path src, scripts, docs, requirements.txt, main.py -DestinationPath package-$timestamp.zip
   ```
4. Record package hash for integrity: `Get-FileHash package-$timestamp.zip`.

## 4. Target Environment Preparation
1. Transfer archive to server (`scp`/`WinSCP`).
2. On server, create deployment directory: `mkdir C:\Services\TalaTG.bot\releases\$timestamp`.
3. Unzip package into release directory.
4. Copy `.env` and session files (`sessions/*.session`) into release directory.
5. Verify Python runtime version matches local (Python 3.10+).

## 5. Deployment Steps
1. **Maintenance Mode**
   - Issue admin panic: `python scripts/send_admin_command.py '{"command":"panic","duration_seconds":600}'` from current environment.
   - Wait for `admin_reports` confirmation.
2. **Service Shutdown**
   - Stop existing engine/agent services (e.g., terminate supervisor tasks or `Stop-Process`).
   - Snapshot database: `Copy-Item data\database.db backups\database-$timestamp.db`.
3. **Install Release**
   - Replace symlink or update service pointer to new release directory.
   - Install dependencies: `pip install -r requirements.txt` (ideally in virtualenv dedicated to release).
   - Run migrations/initialization: `python - <<"PY"
from src.common.db import DatabaseManager
from pathlib import Path
DatabaseManager(Path("data/database.db")).initialize_schema()
PY`.
4. **Start Services**
   - Launch engine: `python main.py engine` (or register Windows Service).
   - Launch agents: `python main.py run`.
   - In separate session, tail `admin_reports` for startup confirmation.
5. **Warm-Up Validation**
   - Trigger dry run using `python scripts/simulate_arbitrage.py --dry-run` (if available) or manual minimal trade via staging groups.
   - Confirm `execution_commands` and `execution_results` flow without errors.
   - Observe Redis keys for expected activity (`redis-cli KEYS 'predictive:*'`).
6. **Resume Trading**
   - Send `resume` admin command: `python scripts/send_admin_command.py '{"command":"resume"}'`.
   - Notify stakeholders that trading is active.

## 6. Post-Deployment Verification
- [ ] Confirm `admin_reports` shows `engine_ready`, `bot_ready`, and no error alerts for 10 minutes.
- [ ] Validate SQLite entries for new trades (spot-check `sqlite3 data/database.db "SELECT COUNT(*) FROM trade_history WHERE created_at >= datetime('now','-10 minutes');"`).
- [ ] Ensure Redis executed cache populates (`redis-cli SCARD executed_trades_cache`).
- [ ] Review logs for speculative trade scheduling and risk manager transitions.
- [ ] Run manual test plan Stage 6–7 steps in production window if acceptable.

## 7. Rollback Plan
1. Trigger `panic` command to halt new trades.
2. Stop services on new release.
3. Restore previous release directory (retain prior zip/hash for reference).
4. Replace database with pre-deployment backup if schema/data issues observed.
5. Restart services using previous binaries.
6. Document rollback in `docs/incidents/` and notify stakeholders.

## 8. Archival & Compliance
- Update `openspec/changes/add-project-roadmap/tasks.md` to reflect completion and run `openspec validate add-project-roadmap --strict` (record output).
- Archive deployment artifacts (zip, logs, transcripts) under `deployments/<timestamp>/`.
- Capture screenshots/log excerpts proving manual validations; attach to change request system.
- Once production stable, prepare archive branch/PR and move change to `openspec/changes/archive/` per governance.

## 9. Appendices
- **Command Reference**: See `docs/operations_runbook.md` for incident playbooks.
- **Credentials Storage**: Follow organization secret management (e.g., Windows Credential Manager or Azure Key Vault). Do not commit `.env`.
- **Contact Sheet**: Maintain up-to-date escalation list in `docs/contacts.md` (create if absent).
