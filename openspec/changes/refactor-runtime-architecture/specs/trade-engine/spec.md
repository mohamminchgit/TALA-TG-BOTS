## MODIFIED Requirements
### Requirement: Destination Exposure Cancellation
The trade engine MUST immediately cancel any destination-side exposure (speculative bait orders or reserved counterparties) when the source opportunity is withdrawn and SHALL include the supervisor confirmation message id in every cancellation command so agents can reply `ن` visibly before deleting posts.

#### Scenario: Cancellation via reply "ن"
- **GIVEN** the engine posted a destination bait order to satisfy `🔵 امین 1 خ 45430`
- **AND** the source agent emits a cancellation event because the trader replied `ن` to the supervisor message
- **THEN** the engine SHALL publish a cancel command that sets `metadata.reply_to_message_id` to the supervisor confirmation id, instruct the destination agent to reply `ن` to that message, and **omit any directive to delete** the speculative post.

#### Scenario: Cancellation via standalone "ن"
- **GIVEN** the engine has an outstanding bait order linked to `🔵 امین 1 خ 45430`
- **AND** the source agent emits a cancellation event due to a standalone `ن`
- **THEN** the engine SHALL cancel the destination bait order, include the supervisor confirmation id in the cancellation metadata, and rely on the supervisor to remove the confirmation after seeing the reply.

#### Scenario: Third-party fulfilment
- **GIVEN** the engine is tracking a bait order for `🔵 امین 1 خ 45430`
- **AND** the source agent reports a supervisor execution message showing another trader fulfilled the order
- **THEN** the engine SHALL cancel any destination bait or reserved counterparty immediately, again providing the supervisor confirmation id so the agent replies visibly without deleting the speculative post.

#### Scenario: Expiry after 60 seconds
- **GIVEN** an order confirmation `🔵 امین 1 خ 45430` remains unfilled for 60 seconds after initial observation
- **AND** the engine has not seen a cancellation or fulfilment
- **THEN** the engine SHALL treat the opportunity as expired, cancel destination exposure with the supervisor confirmation id in metadata, and record the reason as `timeout` for downstream monitoring.

## ADDED Requirements
### Requirement: Supervisor Confirmation Tracking
The engine MUST track the supervisor-issued confirmation message id for every speculative order it posts so that subsequent cancellations and telemetry reference the confirmation instead of the speculative post.

#### Scenario: Confirmation replaces speculative post
- **GIVEN** the destination agent posts `1 خ 400`
- **AND** the supervisor later publishes `🔵 ربات گروه مقصد 1 خ 45400` for the same alias and side
- **THEN** the engine SHALL persist the supervisor confirmation message id, associate it with the pending speculative trade, and expose it via `metadata.reply_to_message_id` when issuing cancel or reconciliation commands.

#### Scenario: Stale confirmation detection
- **GIVEN** the engine previously recorded a supervisor confirmation id for a speculative trade
- **AND** a fresh confirmation arrives matching the same alias and quantity but with a new message id
- **THEN** the engine SHALL update the stored confirmation id to the latest value and ensure future cancellations reference the new message.
