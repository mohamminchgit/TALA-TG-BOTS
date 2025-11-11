## ADDED Requirements
### Requirement: Session Status Visibility
The admin control bot MUST display the session state for each agent (source, destination, admin) and guide operators through renewal when sessions are missing or expired.

#### Scenario: Display session health
- **WHEN** an operator opens the admin dashboard
- **THEN** the bot SHALL show for each agent whether a valid session exists, including last updated time and any pending FloodWait expiration.

#### Scenario: Initiate login from admin bot
- **WHEN** an operator selects “Obtain session” for a bot
- **THEN** the admin bot SHALL send a private prompt indicating the phone number and instructions to enter the verification code, forwarding the code to the backend session service, and confirm success/failure inline.

