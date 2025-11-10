## 1. Implementation
- [ ] 1.1 Add guard in settings to enforce distinct SOURCE/DESTINATION session files
- [ ] 1.2 Fail fast with actionable error when session paths collide
- [ ] 1.3 Update docs to show correct `.env` keys and examples

## 2. Validation
- [ ] 2.1 Local: set both session vars to same path → verify clear startup error
- [ ] 2.2 Local: set distinct session files → verify both agents connect
- [ ] 2.3 Remote: deploy to server and confirm no "database is locked" in logs

## 3. Operations
- [ ] 3.1 Share one-line deploy and restart commands in docs
- [ ] 3.2 Confirm Docker Compose volumes preserve sessions across rebuilds


