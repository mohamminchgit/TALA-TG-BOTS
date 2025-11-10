## 1. Specification
- [x] 1.1 Update telegram-agent requirements to cover reply vs standalone "ن" cancellation detection
- [x] 1.2 Update trade-engine requirements to cancel destination exposure on source cancellation, fulfilment, or timeout

## 2. Implementation
- [x] 2.1 Extend message handler to classify and emit cancellation events for both "ن" patterns
- [x] 2.2 Teach engine to withdraw speculative/reserved orders immediately when cancellation events arrive
- [x] 2.3 Implement 60-second expiry watchdog for unattended source confirmations
- [x] 2.4 Ensure execution command pipeline issues destination "ن" when tearing down bait orders

## 3. Validation
- [x] 3.1 Unit/integration tests simulating reply "ن" and standalone "ن" scenarios
- [x] 3.2 Integration test covering third-party fulfilment (source order consumed by someone else)
- [x] 3.3 Integration test covering 60-second timeout leading to destination cancellation


