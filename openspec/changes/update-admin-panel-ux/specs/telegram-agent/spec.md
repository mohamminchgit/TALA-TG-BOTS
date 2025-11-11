## ADDED Requirements

### Requirement: Supervisor-Addressed Cancellation Acknowledgements
Telegram agents MUST honour the `reply_to_message_id` provided by the engine when executing `cancel_own_order` commands so that the visible `ن` acknowledgement appears on the supervisor confirmation message instead of silently deleting the bot post.

#### Scenario: Cancellation reply targets supervisor confirmation
- **GIVEN** the engine sends a `cancel_own_order` command with `message_id = 12345` and `metadata.reply_to_message_id = 67890`
- **WHEN** the agent executes the command
- **THEN** it SHALL reply with `ن` to message `67890`, respect any configured delay, and only then attempt to delete message `12345`.

#### Scenario: Missing supervisor reference fallback
- **GIVEN** the engine cannot determine the supervisor confirmation id and omits `metadata.reply_to_message_id`
- **WHEN** the agent executes the cancellation
- **THEN** it SHALL log the missing reference, avoid sending `ن`, and proceed with the deletion so operators can spot the gap.
