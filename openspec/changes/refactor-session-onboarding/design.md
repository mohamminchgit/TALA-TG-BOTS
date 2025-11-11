## Context
Agents require Telethon sessions to authenticate. Today, absence of a session forces manual script execution on the server, often during deployment. Repeated login attempts trigger FloodWait errors, causing container thrash and downtime. We need an orchestrated, user-friendly onboarding procedure integrated with deployment tooling and the admin panel. Challenges include secure credential handling (phone/password), staging code entry prompts, persisting session strings in Postgres, and avoiding concurrent login storms.

## Goals / Non-Goals
- Goals:
  - Build an interactive flow that pauses deployment until sessions are confirmed.
  - Surface session state via admin bot with explicit prompts for operator action.
  - Store session strings in Postgres with metadata (timestamp, phone number, bot role).
  - Prevent repeated SendCode requests when FloodWaits occur.
- Non-Goals:
  - Automating phone verification (human must enter code).
  - Replacing Telethon login mechanics (we rely on existing library behaviour).
  - Revamping agent authentication beyond session strings.

## Decisions
- Deployment scripts (PowerShell/Bash) gain a `--ensure-sessions` step that prompts for code, stores session via REST/admin channel, and resumes deployment afterwards.
- Admin bot adds commands to check session status and request manual login for a bot, sending DM prompts to the operator with number and instructions.
- Session storage remains in PostgreSQL; we add audit columns (`session_key`, `phone_number`, `updated_at`).
- FloodWait detection triggers a backoff schedule in the onboarding flow; scripts show remaining wait time before retry.

## Architecture Overview
1. **Bootstrap**: Deployment CLI requests session state for each bot from backend; if missing/expired, push interactive prompts.
2. **Operator input**: CLI or admin bot collects phone and verification code, calls new backend endpoint to finalize login (`LoginSessionService`).
3. **Persistence**: Session string saved to Postgres; metadata surfaced to admin panel dashboards (status = ok/missing/stale).
4. **Resume**: Deployment proceeds when all sessions validated; agents reboot once sessions exist.

## Data Model Changes
- Extend `telethon_sessions` with columns: `phone_number TEXT`, `bot_role TEXT`, `flood_wait_until TIMESTAMPTZ`.
- Add table for session audit logs (optional) capturing authentication attempts, outcome, timestamp.

## Risks / Mitigations
- FloodWait loops if user repeatedly requests codes: mitigate by showing wait time and blocking re-requests until timer expires.
- Security of phone numbers/session strings: ensure transport over secure channel, avoid logging secrets, and restrict admin access.
- Deployment downtime when prompts ignored: allow skip/abort paths, but surface clear warnings.

## Migration Plan
1. Add schema migrations for extended telethon session metadata.
2. Create backend service endpoint + CLI helper to drive login flow.
3. Update admin bot to display session state and trigger login requests.
4. Integrate deployment scripts/CI pipeline to invoke session ensure step before container rollout.
5. Provide documentation and fallback manual command.

