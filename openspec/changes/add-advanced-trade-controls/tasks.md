## 1. Specification
- [x] 1.1 Document fixed-delta spread policy, auto-advertisement handling, and carry limits in `trade-engine` spec delta.
- [x] 1.2 Describe supervisor-aware cancellation flow and configurable auto-`ن` timeout in `telegram-agent` spec delta.
- [x] 1.3 Define admin control bot capabilities, runtime toggles, and telemetry in `admin-control-bot` spec delta.
- [x] 1.4 Record architectural decisions for the multi-service update in `design.md`.

## 2. Implementation
- [x] 2.1 Update engine matchers to enforce delta policy, prioritize existing counterparties, and honour volume caps/opportunity overrides.
- [x] 2.2 Persist supervisor-posted message IDs (both groups) and adjust cancellation logic to quote the supervisor message when posting `ن`.
- [x] 2.3 Exclude auto-advertisement messages from proactive posting while keeping them eligible for opportunistic fills.
- [x] 2.4 Add configuration knobs (env + runtime) for fixed delta, base carry limit, opportunity carry limit, and auto-`ن` delay.
- [x] 2.5 Implement the admin Bot API service with inline keyboards, safe engine pause/resume workflow, and stat reporting.
- [x] 2.6 Extend persistence/Redis schema as needed without blocking engine throughput.

## 3. Validation
- [ ] 3.1 Simulate buy-first and sell-first flows to prove delta enforcement, limited carry, and supervisor-targeted cancellations.
- [ ] 3.2 Exercise admin bot commands (limit updates, pause/resume, auto-`ن` timing) and capture outcomes in validation logs.
