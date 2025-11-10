## ADDED Requirements

### Requirement: Foundation Infrastructure Setup
The system SHALL provide the project skeleton, configuration loader, Redis connectivity, and SQLite schema required to start the Telegram arbitrage bot as described in `openspec/project.md`.

#### Scenario: Project skeleton and dependencies ready
- **GIVEN** the repository is prepared for implementation
- **WHEN** the foundation phase is completed
- **THEN** the directories `src/bot_agent`, `src/engine`, `src/common`, `src/config`, `data`, and `scripts` exist with initial module placeholders
- **AND** configuration values load through `src/config/settings.py` using environment variables and `.env`
- **AND** SQLite tables `config`, `trade_history`, `performance_stats`, and `alert_log` are provisioned under `data/database.db`
- **AND** Redis connectivity helpers are available for reuse by both the engine and bot agents

### Requirement: Telegram Agent Event Pipeline
The system SHALL implement bot agents that parse Trading Supervisor messages, normalize Persian/English numerals, and publish structured events and command results over Redis channels.

#### Scenario: Agents relay group activity to the engine
- **GIVEN** Telethon sessions are configured for source and destination groups
- **WHEN** the agents observe order confirmations, cancellations, executions, or price announcements
- **THEN** they emit normalized payloads on `group_events`
- **AND** they respond to `execution_commands` by posting, replying, or cancelling in-group messages within configured timeouts
- **AND** they publish `execution_results` summarizing success or failure conditions

### Requirement: Immediate Arbitrage Execution
The system SHALL provide an arbitrage engine that maintains an in-memory order book, detects profitable spreads, and orchestrates paired trades across source and destination groups.

#### Scenario: Profitable spread triggers immediate trade
- **GIVEN** the engine tracks active orders from both groups with recent pricing
- **AND** `MINIMUM_PROFIT_SPREAD` is set in configuration
- **WHEN** a new order creates a spread exceeding the minimum profit threshold
- **THEN** the engine issues paired commands with a shared `trade_id` covering both legs
- **AND** it persists executed trade details while caching message IDs to avoid duplicate processing

### Requirement: Predictive Market-Making Strategy
The system SHALL support speculative destination orders that anticipate fills when immediate arbitrage is unavailable, using configurable predictive spread and timeouts.

#### Scenario: Speculative order lifecycle completes successfully
- **GIVEN** the engine detects a one-sided opportunity in the source group without a matching counter-order
- **WHEN** the predictive strategy is enabled and calculates a viable speculative price
- **THEN** the destination agent posts the speculative order and records a `PENDING_DESTINATION_FILL` state with a timeout
- **AND** upon successful fill the engine immediately executes the source leg to capture profit
- **AND** stale or superseded speculative orders are cancelled automatically when timeouts or conflicting fills occur

### Requirement: Risk Management Protocols
The system SHALL implement layered exit strategies, speculative timeouts, and rate-limit crisis handling to minimize exposure when trades fail or bots are throttled.

#### Scenario: Layered exit recovers from partial failure
- **GIVEN** one leg of a paired trade succeeds while the other fails or times out
- **WHEN** the engine evaluates the open position
- **THEN** it executes Layer 2 (Break-Even), Layer 3 (Stop-Loss), and Layer 4 (Emergency Liquidation) strategies according to configured delays
- **AND** it enforces circuit breakers after emergency liquidation to pause trading for the defined duration
- **AND** FloodWait conditions trigger deferred liquidation once rate limits expire

### Requirement: Management Panel Controls
The system SHALL expose a Telegram admin bot that allows authorized users to manage configuration, review statistics, monitor trades, and control bot operations.

#### Scenario: Admin adjusts running system safely
- **GIVEN** an approved admin interacts with the management group
- **WHEN** the admin bot receives dynamic configuration commands or panic/monitor-only toggles
- **THEN** the engine updates parameters stored in SQLite and Redis without restart
- **AND** it publishes performance statistics, alerts, and emergency reports to the management group on demand
- **AND** safe shutdown waits for active trades to conclude before stopping services

### Requirement: Operational Readiness
The system SHALL document manual test flows, operational runbooks, and archival steps so each phase can be validated and promoted through OpenSpec.

#### Scenario: Stage completion is reviewable
- **GIVEN** a development stage reaches completion
- **WHEN** reviewers request evidence
- **THEN** manual end-to-end test scripts, dependency notes, and outage playbooks are available
- **AND** the change includes guidance for archiving the OpenSpec change once deployed
