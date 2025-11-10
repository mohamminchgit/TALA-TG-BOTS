## ADDED Requirements
### Requirement: Inline Configuration Controls
The system SHALL expose an inline-keyboard Telegram bot that lets authorised operators adjust trading parameters without restarting the engine.

#### Scenario: Update carry limit
- **GIVEN** an operator presses the "Carry Limit" button and selects value `1`
- **THEN** the admin bot SHALL persist the new limit, notify the engine, and confirm the change inline.

#### Scenario: Adjust opportunity limit
- **GIVEN** an operator selects an "Opportunity Limit" option `3`
- **THEN** the admin bot SHALL update the corresponding configuration, propagate it to the policy service, and refresh the inline menu to reflect the active value.

#### Scenario: Modify auto-`ن` delay
- **GIVEN** an operator chooses a delay option (e.g., 10 seconds)
- **THEN** the admin bot SHALL apply the setting immediately so that subsequent cancellations honour the new delay.

### Requirement: Safe Engine Pause and Resume
The admin bot SHALL provide controls to pause and resume trading, ensuring no open orders remain before shutdown.

#### Scenario: Pause with pending orders
- **GIVEN** an operator taps "Pause Engine"
- **AND** the engine still tracks active trades
- **THEN** the admin bot SHALL acknowledge the request, instruct the engine to flush pending operations, and only confirm the pause once no open orders remain.

#### Scenario: Resume trading
- **GIVEN** trading was paused via the admin bot
- **WHEN** an operator selects "Resume"
- **THEN** the engine SHALL exit monitor-only mode, clear the pause flag, and the bot SHALL confirm the state change inline.

### Requirement: Operational Status Reporting
The admin bot SHALL present a status dashboard summarising bot connectivity, trade counts, auto advertisement inventory, and profitability metrics on demand.

#### Scenario: View status snapshot
- **WHEN** an operator presses the "Status" button
- **THEN** the admin bot SHALL display current source/destination bot names, online status, buy/sell counts, active auto advertisement count, and aggregated profit/loss since startup.
