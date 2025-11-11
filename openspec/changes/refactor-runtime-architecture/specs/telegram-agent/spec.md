## MODIFIED Requirements
### Requirement: Supervisor-Addressed Cancellation Acknowledgements
Telegram agents MUST honour the `reply_to_message_id` provided by the engine when executing `cancel_own_order` commands so that the visible `ن` acknowledgement appears on the supervisor confirmation message instead of blindly deleting speculative posts.

#### Scenario: Cancellation reply targets supervisor confirmation
- **GIVEN** the engine sends a `cancel_own_order` command with `message_id = 12345` and `metadata.reply_to_message_id = 67890`
- **WHEN** the agent executes the command
- **THEN** it SHALL reply with `ن` to message `67890`, respect any configured delay, and leave message `12345` untouched so the supervisor can remove it.

#### Scenario: Missing supervisor reference fallback
- **GIVEN** the engine cannot determine the supervisor confirmation id and omits `metadata.reply_to_message_id`
- **WHEN** the agent executes the cancellation
- **THEN** it SHALL log the missing reference, avoid sending `ن`, skip deleting message `12345`, and continue so operators can resolve the gap manually.
