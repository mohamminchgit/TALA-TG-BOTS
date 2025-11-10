## ADDED Requirements

### Requirement: Multi-Counterparty Allocation
The system SHALL aggregate profitable opportunities across multiple counterparties at the same or better price before issuing trade commands, splitting volumes as needed.

#### Scenario: Aggregate sell fills for multiple buyers
- **GIVEN** the destination order book contains buyers `🔵 علی 1 خ 45310` and `🔵 حسین 2 خ 45310`
- **AND** the source presents a sell order `🔴 محمد 3 ف 45300`
- **WHEN** the spread exceeds `MINIMUM_PROFIT_SPREAD`
- **THEN** the engine reserves all three units from the source seller
- **AND** issues two destination replies covering 1 unit for علی and 2 units for حسین before mirroring the purchased quantity back to the source group

### Requirement: Order Book Hygiene
The system SHALL purge cancelled or deleted orders from its in-memory and Redis state to avoid acting on phantom opportunities.

#### Scenario: Cancel via "ن" reply removes cached entry
- **GIVEN** order `🔵 حسین 1 خ 45330` is tracked in the destination order book
- **WHEN** حسین cancels the order by replying "ن" (or sending standalone "ن") and the supervisor removes the message
- **THEN** the order book deletes the associated entry and clears Redis indices
- **AND** subsequent opportunity scans ignore that order

## MODIFIED Requirements

### Requirement: Predictive Market-Making Strategy
The system SHALL support speculative destination orders that anticipate fills when immediate arbitrage is unavailable, using configurable predictive spread and timeouts while respecting trading supervisor conventions.

#### Scenario: Speculative order lifecycle completes successfully
- **GIVEN** the engine detects a one-sided opportunity in the source group without a matching counter-order
- **AND** `PREDICTIVE_PRICE_DELTA` controls the absolute price offset while `PREDICTIVE_SUFFIX_DIGITS` defines the trader text length (default four digits)
- **WHEN** the predictive strategy revalidates the order book just before posting and calculates a viable speculative price
- **THEN** the destination agent posts trader-format text using the last `PREDICTIVE_SUFFIX_DIGITS` digits of the computed price (zero-padded) and records a `PENDING_DESTINATION_FILL` state with a timeout
- **AND** upon seeing a supervisor confirmation (even if the counterparty alias matches the original source alias) the engine immediately issues the source leg reply to close the loop
- **AND** stale or superseded speculative orders are cancelled automatically when timeouts or conflicting fills occur

### Requirement: Immediate Arbitrage Execution
The system SHALL provide an arbitrage engine that maintains an in-memory order book, detects profitable spreads, and orchestrates paired trades across source and destination groups.

#### Scenario: Profitable spread triggers immediate trade
- **GIVEN** the engine tracks active orders from both groups with recent pricing and aggregated quantities
- **AND** `MINIMUM_PROFIT_SPREAD` is set in configuration
- **WHEN** available counterparties cover the target quantity at or above the profitable price
- **THEN** the engine issues a batched series of commands that reserves the full quantity on the originating side and replies to each counterparty in descending price priority
- **AND** it persists executed trade details while caching message IDs to avoid duplicate processing

### Requirement: Telegram Agent Event Pipeline
The system SHALL implement bot agents that parse Trading Supervisor messages, normalize Persian/English numerals, publish structured events over Redis channels, and act silently in chat except for authentic trading actions.

#### Scenario: Agents relay group activity to the engine
- **GIVEN** Telethon sessions are configured for source and destination groups
- **WHEN** the agents observe order confirmations, cancellations (including `ن` replies), executions, message deletions, or price announcements
- **THEN** they emit normalized payloads on `group_events`
- **AND** they respond to `execution_commands` by posting, replying, or cancelling in-group messages within configured timeouts without adding acknowledgement chatter or status text, preferring to reply "ن" to supervisor messages when cancelling
- **AND** they publish `execution_results` summarizing success or failure conditions through Redis rather than public messages
