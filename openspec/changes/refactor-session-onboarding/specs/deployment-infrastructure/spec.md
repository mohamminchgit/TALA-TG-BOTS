## ADDED Requirements
### Requirement: Session Onboarding Workflow
Deployment tooling MUST ensure Telegram agent sessions exist before proceeding with container rollout, prompting operators for verification codes when necessary and resuming automatically after sessions are stored.

#### Scenario: Pause deployment for missing session
- **GIVEN** the deployment script detects that the source bot session is absent or expired
- **WHEN** the operator runs `deploy.ps1 --ensure-sessions`
- **THEN** the script SHALL pause container rollout and prompt for the verification code associated with the source phone number, clearly identifying the bot role and destination number.

#### Scenario: Resume after successful login
- **GIVEN** the operator provides the correct verification code (and 2FA if needed)
- **WHEN** the session service persists the new session string in PostgreSQL
- **THEN** the deployment script SHALL resume container rollout and confirm the bot is ready, logging the timestamp of onboarding.

#### Scenario: Handle FloodWait
- **WHEN** Telegram returns a FloodWait error during onboarding
- **THEN** the workflow SHALL display the remaining wait duration, block further code requests until the wait expires, and offer to retry automatically once the timer completes.

