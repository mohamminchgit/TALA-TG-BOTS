## ADDED Requirements
### Requirement: Multi-Service Deployment with PostgreSQL Backbone
The deployment MUST run each core component (engine, source listener, destination listener, admin bot) in separate containers orchestrated by Docker Compose, backed by Redis Streams for messaging and PostgreSQL for persistent storage and Telethon sessions.

#### Scenario: Compose stack definition
- **WHEN** the deployment stack is brought up
- **THEN** Docker Compose SHALL start services `redis`, `postgres`, `engine`, `agent-source`, `agent-destination`, and `admin-bot`, each with dedicated health checks and dependent ordering so agents wait for Redis and Postgres to report ready.

#### Scenario: Persistent storage migration
- **WHEN** the application starts in the new architecture
- **THEN** it SHALL read `DATABASE_URL` and `REDIS_STREAM_*` settings from the environment, connect to PostgreSQL using connection pools, apply migrations if needed, and avoid opening any SQLite files.

#### Scenario: Redis Streams delivery
- **WHEN** an agent publishes group events or consumes execution commands
- **THEN** it SHALL interact with Redis Streams using consumer groups (`XADD`, `XREADGROUP`) so events survive restarts and can be replayed for recovery.

#### Scenario: Automatic image provisioning
- **WHEN** an operator runs the deployment scripts on a fresh host without the `redis:7-alpine` or `postgres:16` images
- **THEN** the tooling SHALL pull the required images (or build if customised) before `docker compose up`, ensuring Redis and Postgres containers are created automatically for the project.
