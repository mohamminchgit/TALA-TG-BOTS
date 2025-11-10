## ADDED Requirements

### Requirement: Telegram Session Isolation
Agents MUST use distinct Telethon session files so that their underlying SQLite databases do not contend for locks.

#### Scenario: Distinct session files
- **WHEN** the system starts with `SOURCE_SESSION_FILE` and `DESTINATION_SESSION_FILE` pointing to different files
- **THEN** both agents SHALL connect without sqlite "database is locked" errors

#### Scenario: Colliding session files
- **WHEN** both agents resolve to the same session file path
- **THEN** the system MUST fail fast with a clear error explaining that session files must be different
- **AND** it MUST NOT attempt to connect either agent to Telegram


