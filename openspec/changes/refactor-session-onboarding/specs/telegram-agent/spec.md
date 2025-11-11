## ADDED Requirements
### Requirement: Session Bootstrap Interface
Telegram agents MUST expose an interface (CLI/REST) allowing the session onboarding workflow to authenticate, provide verification codes, and persist sessions without manual file handling.

#### Scenario: Accept verification code from onboarding flow
- **GIVEN** the session onboarding service has requested a code for the destination bot
- **WHEN** the operator submits the received code
- **THEN** the agent service SHALL finalize the Telethon login, return the session string to the onboarding workflow, and avoid sending additional `SendCodeRequest` calls until FloodWait expires.

