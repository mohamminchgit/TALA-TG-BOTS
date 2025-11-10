# Change: Robust GitHub deployment & richer admin controls

## Why
- GitHub Actions deployment currently fails when `DEPLOY_PATH` is missing, leaving the workflow without a clear error and forcing manual recovery. We must harden the pipeline so pushes to `develop` consistently rebuild the container and restart Docker without touching Telethon sessions.
- Operators need post-deploy transparency: when a release lands, the admin bot should report whether the rollout succeeded and what changed.
- Runtime controls are limited to a handful of spread/carry settings. Admins asked to manage additional engine tunables (predictive timeouts, stop-loss windows, etc.) and to explicitly toggle trading on/off from the bot.

## What Changes
- Update the deployment workflow to validate required secrets, embed the target path, unpack the archive safely, run `docker compose up -d --build`, and invoke a notification script that posts deployment status to `admin_reports`.
- Add a server-side helper (`scripts/admin_notify.py`) so workflows or operators can send structured notifications (success/failure, commit summary) to the admin channel.
- Extend the admin bot dashboard with controls for key `.env` tunables (predictive delta, speculative timeout, stop-loss timers, circuit breaker, monitor mode) and add explicit "Stop Engine" and "Start Engine" actions.
- Teach the engine’s admin service to persist and broadcast the new runtime parameters, and to surface deployment notifications in the admin bot.

## Impact
- Capability `deployment-infrastructure`: GitHub Actions workflow, merge script, new notification helper.
- Capability `admin-control-bot`: inline keyboard updates, deployment notifications, engine power buttons.
- Capability `trade-engine` / admin command service: accept new config keys, persist them, apply to risk manager/predictive components.

## Out of Scope
- Automated health checks or rollback logic beyond existing docker-compose restart.
- UI/UX changes for the Telegram trading agents.
- Historical audit trail of deployments (notifications are real-time only).

