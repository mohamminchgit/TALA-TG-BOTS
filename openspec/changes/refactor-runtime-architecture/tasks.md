## 1. Implementation
- [x] 1.1 Update destination agent classification to publish supervisor confirmation ids for self-issued orders and persist them in the engine trade tracker.
- [x] 1.2 Change `cancel_own_order` handling so agents reply `ن` to the supervisor confirmation without deleting the original speculative message; add telemetry to confirm behaviour.
- [x] 1.3 Introduce PostgreSQL support (connection pools, migrations) and migrate existing SQLite tables and data.
- [x] 1.4 Replace Telethon’s SQLite session with a Postgres-backed session store for each agent container.
- [x] 1.5 Switch Redis pub/sub channels to Streams with consumer groups across engine, agents, and admin bot.
- [x] 1.6 Split Docker Compose into dedicated services (engine, source agent, destination agent, admin bot) and add Postgres service plus health checks.
- [x] 1.7 Update deployment scripts to pull/build required images (`redis:7-alpine`, `postgres:16`) when absent, adjust environment examples to cover new database settings, and remove references to the external Redis host.
- [x] 1.8 Execute end-to-end regression tests in a staging environment: speculative order fill, cancellation via `ن`, stream replay after restart, and database failover scenarios.
