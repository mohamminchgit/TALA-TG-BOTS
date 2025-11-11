## MODIFIED Requirements
### Requirement: Inline Configuration Controls
The system SHALL present a fully Persian inline dashboard that groups controls into the specified rows, uses inline alerts for feedback, and only reflects configuration changes after the engine confirms the applied values.

#### Scenario: Persian control layout
- **GIVEN** an authorised operator issues `/start` or the dashboard refreshes automatically
- **THEN** the message SHALL include the Persian sections:
  - `وضعیت ربات: <indicator> <state>`
  - `📊 آمار کلی` with today’s profit, executed trade count, and current open-trade count
  - `⚙️ تنظیمات فعلی موتور` listing spread, carry limits, timeout pairs, stop-loss offset, and circuit breaker duration
- **AND** the inline keyboard SHALL render the rows in order:
  - Row 1: `[🔴 خاموش کردن موتور|🟢 روشن کردن موتور]` (context-aware single toggle), `[📊 نمایش آمار کامل]`
  - Row 2: `[تغییر اسپرد (Δ)]`, `[تغییر محدودیت‌ها]`
  - Row 3: `[تنظیم مهلت‌ها (Timeouts)]`
  - Row 4: `[❓ راهنما]`, `[🔄 بازگشت به تنظیمات پیش‌فرض]`

#### Scenario: Inline alert feedback
- **WHEN** the operator selects any configuration option (e.g., a new spread delta)
- **THEN** the bot SHALL answer with `event.answer(..., alert=True)` describing the change in Persian without sending a new chat message
- **AND** the dashboard SHALL refresh only after the engine emits a `config_updated` payload so displayed values match the applied configuration.

#### Scenario: Reset defaults
- **WHEN** the operator taps `🔄 بازگشت به تنظیمات پیش‌فرض`
- **THEN** the bot SHALL replay the captured baseline configuration to the engine, wait for the corresponding `config_updated` confirmation, and refresh the dashboard showing the restored defaults in Persian.

#### Scenario: Engine power toggle
- **GIVEN** trading is currently allowed
- **WHEN** the operator presses `🔴 خاموش کردن موتور`
- **THEN** the bot SHALL request a safe pause, surface an inline alert confirming the request, and once the engine reports completion, change the button label to `🟢 روشن کردن موتور` with the dashboard status updated in Persian.
- **AND WHEN** the engine is paused, pressing the same button SHALL issue the resume command, alert the operator, and restore the `🔴 خاموش کردن موتور` label after confirmation.

### Requirement: Safe Engine Pause and Resume
The admin bot SHALL ensure engine pause/resume flows honour outstanding work while keeping the chat output in Persian.

#### Scenario: Pause with pending orders
- **GIVEN** an operator taps `🔴 خاموش کردن موتور`
- **AND** the engine reports active trades or pending speculative orders
- **THEN** the bot SHALL acknowledge the request via inline alert, instruct the engine to clear outstanding work, and only switch the dashboard state to “🟡 در حال توقف ایمن” once the engine reports it is safe to pause.

#### Scenario: Toggle to resume
- **GIVEN** the dashboard currently shows `وضعیت ربات: 🔴 متوقف`
- **WHEN** the operator taps `🟢 روشن کردن موتور`
- **THEN** the bot SHALL request resume, alert the operator in Persian that trading is reactivating, and update the dashboard status to `🟢 روشن (در حال نظارت)` after the engine confirmation.

### Requirement: Operational Status Reporting
The admin bot SHALL display live Persian summaries of engine state, aggregated performance metrics, and configuration values sourced directly from the engine snapshot.

#### Scenario: Display aggregated metrics
- **WHEN** the dashboard refreshes
- **THEN** it SHALL show today’s profit (with currency symbol if available), executed trade count, current open-trade count, and outstanding order counts per group exactly as provided by the engine.

#### Scenario: Request full stats
- **WHEN** the operator taps `📊 نمایش آمار کامل`
- **THEN** the bot SHALL answer with a Persian summary derived from the latest status snapshot, covering source/destination aliases, monitor-only flag, open advertisement totals, cumulative trade profit, and configuration deltas.

## ADDED Requirements
### Requirement: Persian Help Command
The admin bot SHALL respond to `/help` (or the inline `❓ راهنما` button) with a Persian guide explaining each dashboard section and button.

#### Scenario: Help command output
- **WHEN** an authorised operator sends `/help`
- **THEN** the bot SHALL send a formatted Persian message describing the meaning of the status banner, each statistics line, and every control button, including warnings for reset-to-default and engine pause actions.
