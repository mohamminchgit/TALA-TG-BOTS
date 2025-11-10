## 1. Workflow Hardening
- [ ] 1.1 Update `.github/workflows/deploy-develop.yml` to validate secrets, set default deploy path, and run docker compose reliably
- [ ] 1.2 Bundle deployment metadata (commit, change summary) and exclude sessions during archive
- [ ] 1.3 Add post-deploy notification hook invoking a new admin notification script on the server

## 2. Runtime Tooling
- [ ] 2.1 Introduce `scripts/admin_notify.py` for publishing structured events to `admin_reports`
- [ ] 2.2 Extend admin command service to accept/persist new tunables (predictive timeout, stop loss windows, circuit breaker, monitor toggle)
- [ ] 2.3 Enhance admin bot UI with controls for the new settings plus explicit engine stop/start buttons
- [ ] 2.4 Ensure admin bot surfaces deployment success/failure messages

## 3. Documentation & Defaults
- [ ] 3.1 Document the required GitHub secrets/variables and new env keys in `openspec/project.md`
- [ ] 3.2 Provide `.env.example` defaults for newly exposed parameters
- [ ] 3.3 Validate `openspec` change (`openspec validate improve-auto-deploy-admin --strict`)

