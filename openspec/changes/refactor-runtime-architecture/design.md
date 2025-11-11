## Context
Destination agents currently issue speculative orders, watch the supervisor repost them, and then record execution through Redis. Because we do not persist the supervisor message id, later cancellation commands fall back to deleting the speculative message id directly. At the same time, both Telethon and the engine persist state in SQLite files that are shared across coroutines. Under high traffic Telethon raises `sqlite3.OperationalError: database is locked`, causing agents to disconnect.

The user wants a more resilient architecture: each listener in its own container, Redis Streams for durable event delivery, and PostgreSQL as the shared durable store (including Telethon sessions) so file locks disappear. We must also change the cancellation flow so we only reply `ن` to the supervisor confirmation and let the supervisor delete the messages.

## Goals / Non-Goals
- Goals: capture supervisor confirmation ids for speculative orders, stop bot-side deletions after sending `ن`, move persistent storage from SQLite to PostgreSQL, migrate Telethon sessions to Postgres, update Docker Compose to run engine/agents/admin as separate services, and switch message ingestion to Redis Streams for replayability.
- Non-Goals: rewiring trading logic, changing risk algorithms, or altering Redis channel schemas outside the shift to Streams. We also do not redesign the admin UX (covered in another change) except to ensure new status data is available.

## Decisions
- Decision: when a speculative order is confirmed by the supervisor, the destination agent will publish the new message id in the group event payload; the engine’s trade tracker will persist that confirmation id and expose it in cancellation metadata. This allows `cancel_own_order` commands to reference the supervisor message explicitly.
- Decision: modify `CommandExecutor._handle_cancel` so it only sends `ن` to `metadata.reply_to_message_id` and skips deleting `message_id`, relying on the supervisor to handle cleanup.
- Decision: replace SQLite with PostgreSQL. A new module `common/postgres.py` will provide async (asyncpg) and sync accessors; engine services (`AdminCommandService`, `RiskManager`, trade history writers) will query Postgres via connection pools. Configuration persistence moves to a `config` table in Postgres with the same schema but using proper transactions.
- Decision: adopt Redis Streams (`xadd`/`xreadgroup`) for `group_events`, `execution_commands`, and `execution_results`. Each service runs as a consumer group member, enabling replay after restarts.
- Decision: split Docker Compose into services: `engine`, `agent_source`, `agent_destination`, `admin_bot`, `redis`, `postgres`. Each bot container mounts only its session environment variables; Telethon uses a Postgres-backed session via `telethon.sessions.aio.PostgresSession`.
- Decision: manage schema migrations with Alembic (new folder under `deployment/db_migrations`) to version Postgres tables.

## Architecture Overview
1. **Event Flow**
   - Agents read Telegram updates, classify them, and append events to the `group_events` Redis Stream with a consumer id equal to the agent name.
   - The engine service reads from the stream consumer group, updates Postgres tables (`orders`, `trades`, `config`), and records supervisor confirmation ids on speculation success.
   - Cancellation commands embed `reply_to_message_id` (supervisor id) and are appended to the `execution_commands` stream. Agents read commands via consumer groups, ensuring at-least-once delivery.
2. **Persistence**
   - Postgres hosts tables for `config`, `trade_history`, `performance_stats`, `alert_log`, plus new tables for `orders` and Telethon session data. Telethon uses a dedicated schema (`telethon_sessions`) with connection URL from environment variables.
   - Redis continues to store transient signals (e.g., pending predictive trades) but long-lived data moves to Postgres. Redis itself now runs as an internal container managed by Docker Compose rather than an external host service.
3. **Deployment**
   - Docker Compose defines services:
     - `redis`: official `redis:7-alpine` image, mounted volume for persistence, health check, and `restart: unless-stopped`. Deployment scripts ensure the image is pulled locally if absent before the stack starts.
     - `postgres`: official `postgres:16` image with mounted volume, health check, and automatic `docker pull` if missing.
     - `engine`: runs the arbitrage engine process only.
     - `agent-source`, `agent-destination`: run individual bot agents.
     - `admin-bot`: runs the admin control bot.
   - Shared environment variables include `DATABASE_URL`, `REDIS_URL`, stream names, and per-agent credentials. Compose replaces the previous external Redis dependency; installation scripts bootstrap required images and create containers automatically.

## Data Model Changes
- Create Postgres tables mirroring existing SQLite schema plus `orders` (tracks supervisor message ids, speculative posts, confirmation ids) and `engine_state` (monitor-only flag, last pause time).
- Provide migrations to seed default config values.
- Update persistence calls in `RiskManager`, `AdminCommandService`, and predictive market maker to use Postgres transactions.

## Cancellation Flow Updates
1. The destination agent records speculation posts (message id 1414) and, upon seeing the supervisor confirmation (message id 1419) that matches its alias and emoji, publishes an event `confirmation_message_id`.
2. The trade tracker stores both the speculative message id and the supervisor confirmation id.
3. When the engine issues `cancel_own_order`, it sets `message_id` to the speculative post (for optional telemetry) but `metadata.reply_to_message_id` to the supervisor confirmation id. Agents reply `ن` to the supervisor confirmation and **do not call `delete_messages`**.
4. Deletion is left to the human supervisor, preserving audit trail and aligning with group expectations.

## Migration Plan
1. Introduce Postgres configuration flags alongside existing SQLite, implement dual-write during transition (optional feature flag) to validate queries.
2. Deploy Postgres and run Alembic migrations.
3. Switch Telethon sessions to Postgres by updating credentials and migrating existing session data (one-time script).
4. Enable Redis Streams with consumer groups; update services to handle new APIs while preserving backward compatibility via feature flag.
5. Remove SQLite usage, delete the old `data/database.db` file, and update documentation.

## Risks / Mitigations
- **Risk:** Telethon Postgres session support may require custom patching. Mitigation: use official `PostgresSession` class and run soak tests; fallback to manual session storage if critical issues arise.
- **Risk:** Redis Streams increase operational complexity. Mitigation: reuse existing Redis cluster, add metrics dashboards, and provide instructions for trimming streams (`XTRIM`).
- **Risk:** Multi-container deployment needs orchestration changes. Mitigation: update deployment scripts (`deploy.ps1`) to bring up the new services and add health checks to ensure dependencies are ready before agents start.

## Open Questions
- Do we need to support rolling upgrades where some agents still use SQLite sessions during the transition? If yes, we need a compatibility shim.
- Should we introduce Kubernetes manifests alongside Docker Compose to handle scaling listeners automatically?
