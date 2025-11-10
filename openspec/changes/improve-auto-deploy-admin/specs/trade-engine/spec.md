## MODIFIED Requirements

### Requirement: Admin command processing
The engine SHALL consume admin commands and apply runtime configuration updates without restarts.

#### Scenario: Apply extended tunables
- **WHEN** an `update_config` command includes any of the keys `speculative_trade_timeout_seconds`, `predictive_price_delta`, `predictive_suffix_digits`, `exit_break_even_timeout_seconds`, `exit_stop_loss_timeout_seconds`, `stop_loss_price_offset`, `circuit_breaker_pause_seconds`, `monitor_only`, or `auto_n_delay_seconds`
- **THEN** the engine SHALL validate the values, apply them to the predictive market maker and risk manager, persist them to the config table, and emit a `config_updated` admin report

#### Scenario: Deployment event bridging
- **WHEN** the deployment helper publishes a `deployment` event with fields `{status, commit, summary}`
- **THEN** the engine SHALL forward the payload unchanged to `admin_reports` so the admin bot can notify operators

