## 1. Discovery & Validation
- [x] 1.1 Analyse current deployment scripts and identify points to hook the session check.
- [x] 1.2 Document the manual session onboarding pain points (FloodWait, missing env, duplicate scripts).

## 2. Session Lifecycle Service
- [x] 2.1 Extend Postgres schema with session metadata (owner phone, role, timestamps).
- [x] 2.2 Implement backend service/CLI to request code, confirm login, and persist session.
- [x] 2.3 Handle FloodWait and retry messaging gracefully.

## 3. Deployment & Admin Integration
- [x] 3.1 Update deployment scripts (`deploy.ps1`, CI pipeline) to pause for session ensure step.
- [x] 3.2 Enhance admin bot to display session status and initiate login prompts.
- [x] 3.3 Provide automation tests or manual checklist to verify end-to-end onboarding.

## 4. Documentation
- [x] 4.1 Update operations runbook with new workflow.
- [x] 4.2 Add troubleshooting guide for session onboarding (FloodWait, wrong code, missing phone).

