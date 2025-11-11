## 1. Implementation
- [ ] 1.1 Localise the admin dashboard text into Persian, implement the requested message layout, and reorganise the inline keyboard rows with the new toggle button.
- [ ] 1.2 Replace chat notifications with inline alerts, defer state refresh until `config_updated` events arrive, and add the `/help` command output.
- [ ] 1.3 Capture baseline configuration at startup and wire a reset button that replays those defaults through the engine and refreshes the dashboard.
- [ ] 1.4 Extend `AdminCommandService` status snapshots to include open trade counts, honour the reset command, and always emit actual applied values.
- [ ] 1.5 Ensure cancellation commands carry the supervisor confirmation id and update the agent cancellation handler to reply `ن` to that id before deleting the message.
- [ ] 1.6 Manual QA in a sandbox chat covering config updates, reset flow, `/help`, and cancellation of speculative orders.
