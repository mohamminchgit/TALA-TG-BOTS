## MODIFIED Requirements
### Requirement: Destination Exposure Cancellation
The trade engine MUST immediately cancel any destination-side exposure (speculative bait orders or reserved counterparties) when the source opportunity is withdrawn and SHALL include the supervisor confirmation message id in every cancellation command so agents can reply `ن` visibly before deleting posts.

#### Scenario: Cancellation via reply "ن"
- **GIVEN** the engine posted a destination bait order to satisfy `🔵 امین 1 خ 45430`
- **AND** the source agent emits a cancellation event because the trader replied `ن` to the supervisor message
- **THEN** the engine SHALL publish a cancel command that sets `metadata.reply_to_message_id` to the supervisor confirmation id, instruct the destination agent to reply `ن` to that message, and remove the bait exposure.

#### Scenario: Cancellation via standalone "ن"
- **GIVEN** the engine has an outstanding bait order linked to `🔵 امین 1 خ 45430`
- **AND** the source agent emits a cancellation event due to a standalone `ن`
- **THEN** the engine SHALL cancel the destination bait order, include the supervisor confirmation id in the cancellation metadata, and mark the opportunity closed.

#### Scenario: Third-party fulfilment
- **GIVEN** the engine is tracking a bait order for `🔵 امین 1 خ 45430`
- **AND** the source agent reports a supervisor execution message showing another trader fulfilled the order
- **THEN** the engine SHALL cancel any destination bait or reserved counterparty immediately, again providing the supervisor confirmation id to ensure the visible `ن` acknowledgement.

#### Scenario: Expiry after 60 seconds
- **GIVEN** an order confirmation `🔵 امین 1 خ 45430` remains unfilled for 60 seconds after initial observation
- **AND** the engine has not seen a cancellation or fulfilment
- **THEN** the engine SHALL treat the opportunity as expired, cancel destination exposure with the supervisor confirmation id in metadata, and record the reason as `timeout` for downstream monitoring.

## ADDED Requirements
### Requirement: Configuration State Confirmation
The engine SHALL acknowledge admin updates with the actual applied configuration values, support a reset-to-default command, and guarantee that status snapshots expose live exposure metrics for the dashboard.

#### Scenario: Applied values echoed
- **WHEN** the admin bot requests a new spread delta or timeout value
- **THEN** the `config_updated` report SHALL contain the applied numbers from the live policy/risk managers, and these values SHALL match what the admin bot renders.

#### Scenario: Reset to defaults command
- **WHEN** the admin bot issues a reset command with the captured baseline configuration
- **THEN** the engine SHALL reapply those defaults to its policy, predictive, and risk subsystems, persist them to storage, and emit a `config_updated` report with the restored values.

#### Scenario: Status snapshot includes exposure metrics
- **WHEN** the admin bot sends a status request or the engine broadcasts a status update
- **THEN** the snapshot SHALL include counts for active trades, pending predictive trades, outstanding orders per group, advertisement totals, today’s profit, and trade count so the Persian dashboard can render all requested sections.
