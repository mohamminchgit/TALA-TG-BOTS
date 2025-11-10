## ADDED Requirements

### Requirement: Supervisor Compliance Messaging
The system SHALL ensure bot-originated chat messages mimic raw trader inputs so the human supervisor can reformat them without revealing automation.

#### Scenario: Speculative order uses trader format
- **GIVEN** the predictive strategy decides to bait the destination group with a speculative sell or buy
- **WHEN** the destination agent posts the speculative message
- **THEN** the message body is emitted as `<quantity><side><price_suffix>` without emojis, aliases, or bot-identifying prefixes
- **AND** the message uses normalized digits that the Trading Supervisor recognizes and rewrites

## MODIFIED Requirements

### Requirement: Telegram Agent Event Pipeline
The system SHALL implement bot agents that parse Trading Supervisor messages, normalize Persian/English numerals, publish structured events over Redis channels, and act silently in chat except for authentic trading actions.

#### Scenario: Agents relay group activity to the engine
- **GIVEN** Telethon sessions are configured for source and destination groups
- **WHEN** the agents observe order confirmations, cancellations, executions, or price announcements
- **THEN** they emit normalized payloads on `group_events`
- **AND** they respond to `execution_commands` by posting, replying, or cancelling in-group messages within configured timeouts without adding acknowledgement chatter or status text
- **AND** they publish `execution_results` summarizing success or failure conditions through Redis rather than public messages

### Requirement: Predictive Market-Making Strategy
The system SHALL support speculative destination orders that anticipate fills when immediate arbitrage is unavailable, using configurable predictive spread and timeouts while respecting trading supervisor conventions.

#### Scenario: Speculative order lifecycle completes successfully
- **GIVEN** the engine detects a one-sided opportunity in the source group without a matching counter-order
- **WHEN** the predictive strategy is enabled, revalidates the order book just before posting, and calculates a viable speculative price
- **THEN** the destination agent posts a trader-format speculative message (`<quantity><side><price_suffix>`) and records a `PENDING_DESTINATION_FILL` state with a timeout
- **AND** upon successful fill the engine immediately executes the source leg to capture profit
- **AND** stale or superseded speculative orders are cancelled automatically when timeouts or conflicting fills occur
