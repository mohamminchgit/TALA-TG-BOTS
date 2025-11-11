# Change: Refactor Runtime Architecture and Cancellation Flow

## Why
- Destination agents currently delete their own speculative posts after replying with `ن`. Human supervisors already remove the confirmation after seeing the reply, so the self-deletion hides evidence of the cancellation and conflicts with trading etiquette.
- The bot has no persistent record of the supervisor-issued confirmation message id; when the confirmation replaces the speculative post, later cancellation commands cannot reference the correct message id, so replies target the wrong message.
- Telethon sessions and engine persistence rely on SQLite files shared between multiple async tasks. Under load, SQLite frequently raises `OperationalError: database is locked`, disconnecting listeners and halting trading.
- Running the entire engine plus both listeners inside a single container compounds contention: all components share the same local files and cannot scale independently when traffic spikes.
- Redis currently runs outside the Docker environment on the host. This external dependency complicates setup and troubleshooting; we want Redis packaged alongside the app so deployments are self-contained.

## What Changes
- Track supervisor confirmation message ids for self-posted orders so the engine can direct cancellations to the confirmation rather than the original speculative post, and update agent behaviour to stop deleting the post after replying with `ن`.
- Redesign the runtime architecture around Redis Streams and PostgreSQL: retire SQLite and Telethon’s embedded session database, run each listener (source, destination, admin) and the engine in dedicated containers, and manage them through Docker Compose.
- Introduce a shared Postgres schema for configuration, trade history, and telemetry, migrate Telethon sessions to Postgres-backed storage, and ship Redis as a managed container within the same Compose stack so no external service is required.
- Update deployment tooling and configuration management to provision the new services, define health checks, automatically pull Redis/Postgres images if missing, and expose connection settings via environment variables.

## Impact
- Affected specs: `telegram-agent`, `trade-engine`, `deployment-infrastructure`
- Affected code: `src/bot_agent/services/command_executor.py`, `src/engine/core/predictive_market_maker.py`, `src/engine/core/trade_tracker.py`, `src/engine/services/admin_service.py`, `src/common/db.py`, deployment scripts, Docker Compose, and configuration modules handling database connections and Redis streams.
