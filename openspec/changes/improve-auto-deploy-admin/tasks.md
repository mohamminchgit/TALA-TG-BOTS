## 1. Workflow Hardening
- [x] 1.1 Update `.github/workflows/deploy-develop.yml` to validate secrets, set default deploy path, and run docker compose reliably
- [x] 1.2 Bundle deployment metadata (commit, change summary) and exclude sessions during archive
- [x] 1.3 Add post-deploy notification hook invoking a new admin notification script on the server

## 2. Runtime Tooling
- [x] 2.1 Introduce `scripts/admin_notify.py` for publishing structured events to `admin_reports`
- [x] 2.2 Extend admin command service to accept/persist new tunables (predictive timeout, stop loss windows, circuit breaker, monitor toggle)
- [x] 2.3 Enhance admin bot UI with controls for the new settings plus explicit engine stop/start buttons
- [x] 2.4 Ensure admin bot surfaces deployment success/failure messages

## 3. Documentation & Defaults
- [x] 3.1 Document the required GitHub secrets/variables and new env keys in `openspec/project.md`
- [x] 3.2 Provide `.env.example` defaults for newly exposed parameters
- [x] 3.3 Validate `openspec` change (`openspec validate improve-auto-deploy-admin --strict`)

