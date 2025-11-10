## ADDED Requirements
### Requirement: Supervisor-Aware Cancellation Replies
Telegram agents SHALL reply with `ن` to the supervisor-issued confirmation message when cancelling orders, rather than to the raw bot-authored post.

#### Scenario: Cancel speculative post without supervisor fill
- **GIVEN** the destination bot posts `1ف910`
- **AND** the trading supervisor reformats it as `🔴 ربات گروه مقصد 1 ف 45910`
- **WHEN** the engine orders a cancellation after the configured timeout
- **THEN** the destination bot SHALL reply `ن` to the supervisor message ID before deleting the order.

#### Scenario: Supervisor message missing
- **GIVEN** the bot cannot locate the supervisor message ID for an outstanding order
- **WHEN** the engine requests cancellation
- **THEN** the bot SHALL log the anomaly and fall back to deleting the order without sending `ن`, while reporting the condition via execution results.

### Requirement: Configurable Auto-`ن` Delay
Telegram agents SHALL delay auto-cancellation replies by a configurable duration and expose runtime updates.

#### Scenario: Honour configured delay
- **GIVEN** `AUTO_N_DELAY_SECONDS` is set to 5
- **WHEN** an order must be cancelled automatically
- **THEN** the agent SHALL wait approximately five seconds before issuing the supervisor-targeted `ن` reply and deletion.

#### Scenario: Runtime update via admin controls
- **GIVEN** an operator adjusts the auto-`ن` delay to 10 seconds via the admin surface
- **THEN** subsequent cancellations SHALL use the new delay without restarting the bots.
