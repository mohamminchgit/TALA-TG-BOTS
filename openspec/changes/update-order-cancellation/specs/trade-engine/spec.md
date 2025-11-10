## ADDED Requirements

### Requirement: Destination Exposure Cancellation
The trade engine MUST immediately cancel any destination-side exposure (speculative bait orders or reserved counterparties) when the source opportunity is withdrawn through cancellation, third-party fulfilment, or natural expiry.

#### Scenario: Cancellation via reply "ن"
- **GIVEN** the engine posted a destination bait order to satisfy `🔵 امین 1 خ 45430`
- **AND** the source agent emits a cancellation event because the trader replied `ن` to the supervisor message
- **THEN** the engine SHALL publish a cancel command to the destination agent to reply `ن` to its bait message and release the opportunity

#### Scenario: Cancellation via standalone "ن"
- **GIVEN** the engine has an outstanding bait order linked to `🔵 امین 1 خ 45430`
- **AND** the source agent emits a cancellation event due to a standalone `ن`
- **THEN** the engine SHALL cancel the destination bait order and mark the opportunity closed

#### Scenario: Third-party fulfilment
- **GIVEN** the engine is tracking a bait order for `🔵 امین 1 خ 45430`
- **AND** the source agent reports a supervisor execution message showing another trader fulfilled the order
- **THEN** the engine SHALL cancel any destination bait or reserved counterparty immediately to avoid holding an unpaired position

#### Scenario: Expiry after 60 seconds
- **GIVEN** an order confirmation `🔵 امین 1 خ 45430` remains unfilled for 60 seconds after initial observation
- **AND** the engine has not seen a cancellation or fulfilment
- **THEN** the engine SHALL treat the opportunity as expired, cancel destination exposure, and release any reserved inventory
- **AND** it SHALL record the reason as `timeout` for downstream monitoring

