## MODIFIED Requirements

### Requirement: CI-triggered Docker deployment
The GitHub Actions workflow MUST package the application (excluding secrets and Telethon sessions), upload it to the Linux host, unpack into the deployment path, rebuild the Docker Compose stack, and report the outcome.

#### Scenario: Secrets validated before deploy
- **WHEN** the workflow starts on a `develop` push
- **THEN** it SHALL fail fast with a descriptive message if `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, or `DEPLOY_PATH` are missing

#### Scenario: Sessions preserved
- **WHEN** the archive is created
- **THEN** `.env`, `sessions/`, `data/`, and other sensitive assets SHALL be excluded so running credentials persist on the server

#### Scenario: Deployment notification
- **WHEN** the remote `docker compose up -d --build` succeeds or fails
- **THEN** the workflow SHALL invoke `scripts/admin_notify.py` on the server to publish a `deployment` event containing the commit SHA, author, and commit subject to the admin channel

### Requirement: Merge .env template into server configuration
`deployment/merge-env.sh` SHALL merge `.env.example` into the live `.env` file, preserving existing values and appending new keys during CI deployments.

#### Scenario: New env key added
- **WHEN** `.env.example` introduces a key that does not exist in the server `.env`
- **THEN** the merge script SHALL add the key with the example value without overwriting existing secrets

