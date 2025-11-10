## MODIFIED Requirements

### Requirement: Inline Configuration Controls
The system SHALL expose an inline-keyboard Telegram bot that lets authorised operators adjust trading parameters without restarting the engine.

#### Scenario: Update predictive timeout
- **WHEN** an operator selects "Speculative Timeout" → `60s`
- **THEN** the admin bot SHALL publish an `update_config` command with `speculative_trade_timeout_seconds=60`, refresh the dashboard, and confirm the change inline

#### Scenario: Adjust risk timers
- **WHEN** an operator picks `5s` for "Break-even Wait" or `15s` for "Stop-loss Wait"
- **THEN** the bot SHALL update `EXIT_STRATEGY_TIMEOUT_SECONDS` or `EMERGENCY_TIMEOUT_SECONDS` respectively, persist the new value, and notify the operator of the applied change

#### Scenario: Toggle monitor/engine state
- **WHEN** an operator taps "🔴 Stop Engine"
- **THEN** the bot SHALL request an engine shutdown via the admin command channel and acknowledge the request
- **AND WHEN** an operator taps "🟢 Start Engine"
- **THEN** the bot SHALL send a resume command (or clear monitor-only mode) and confirm trading has resumed

### Requirement: Operational Status Reporting
The admin bot SHALL present a status dashboard summarising bot connectivity, trade counts, auto advertisement inventory, and profitability metrics on demand, and relay operational notifications.

#### Scenario: Deployment notification
- **WHEN** the deployment workflow publishes a `deployment` report
- **THEN** the admin bot SHALL forward a message containing the status (success/failure), commit SHA, author, and subject to the privileged chat

 