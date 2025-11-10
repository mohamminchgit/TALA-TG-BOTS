# Change: Enforce Telegram session isolation and prevent SQLite lock crashes

## Why
Observed `sqlite3.OperationalError: database is locked` during startup. Root cause is multiple Telethon clients contending for the same `.session` SQLite file. Engine never needs Telegram sessions; only the two agents should access distinct session files. When both agents point to the same path due to misconfiguration, Telethon's SQLite database is locked, causing startup failures.

## What Changes
- Add a startup validation that ensures `SOURCE_SESSION_FILE` and `DESTINATION_SESSION_FILE` resolve to two different files; fail fast with a clear error message if they are identical.
- Clarify env var names and examples in docs; require two distinct paths and show how to set them in `.env`.
- Keep single-container deployment; no architecture split needed for this fix.

## Impact
- Affects `telegram-agent` capability (session handling and validation).
- Affects deployment docs (configuration section).

## Out of Scope
- Migrating session storage away from Telethon's SQLite.
- Replacing SQLite with MySQL for the app database.


