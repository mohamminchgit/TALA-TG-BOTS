# Change: Streamlined Session Onboarding & Deployment Pause

## Why
- Deployments frequently fail because Telethon sessions are missing; manual scripts require terminal work on the server, are error‑prone, and trigger FloodWait loops while the agents repeatedly request login codes.
- Operators want the deployment flow to pause automatically, request the login code for each bot in order, and resume only after the session is persisted, without hunting for environment variables or running ad‑hoc Python scripts.
- The admin panel should reflect missing sessions and help with recovery, instead of silently rebooting agents.

## What Changes
- Introduce a controlled onboarding flow that pauses deployment/downtime scripts until required sessions exist, prompts for the verification code per phone number, stores the resulting string in PostgreSQL, and reports status via admin bot/CLI.
- Provide guardrails in deployment tooling (and admin panel) to detect missing/expired sessions and surface interactive prompts to operators.
- Persist session state in PostgreSQL with audit metadata and expose recovery commands.

## Impact
- Affected specs: `deployment-infrastructure`, `admin-control-bot`, `telegram-agent`
- Affected code: deployment scripts (PowerShell/Bash), admin bot controller, session storage helpers (`scripts/store_session.py`), and CI workflow automation.

