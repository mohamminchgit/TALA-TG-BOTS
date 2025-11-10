## ADDED Requirements

### Requirement: Cancellation Detection for "ن"
Telegram agents MUST detect trader cancellations triggered by the Persian letter "ن", whether the message is a direct reply to a supervisor confirmation or a standalone post in the chat, and publish normalized cancellation events to the engine.

#### Scenario: Reply cancellation
- **GIVEN** the supervisor previously confirmed an order as `🔵 امین 1 خ 45430`
- **AND** the trader replies to that confirmation with the single character `ن`
- **THEN** the source agent SHALL emit a cancellation event that references the original message id so the engine can withdraw any mirrored exposure

#### Scenario: Standalone cancellation
- **GIVEN** the supervisor confirmed an order for `🔵 امین 1 خ 45430`
- **AND** the trader later posts a standalone `ن` message (not a reply)
- **THEN** the source agent SHALL emit a cancellation event tied to the most recent active confirmation for that trader so the engine can withdraw mirrored exposure
- **AND** if the agent cannot confidently map the standalone `ن` to an active order, it SHALL log and ignore it instead of attempting a blind cancellation

