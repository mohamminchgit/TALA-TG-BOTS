## 1. Specification
- [x] 1.1 Update `project-roadmap` spec with trading supervisor compliance requirements for agent messaging.
- [x] 1.2 Describe predictive market-making text formatting rules and pre-flight checks in the spec delta.

## 2. Implementation
- [x] 2.1 Remove explicit acknowledgement posts from source agent command handling while keeping internal logging.
- [x] 2.2 Teach predictive command builder to emit raw trader-format text (`<qty><side><priceSuffix>`) instead of supervisor-formatted phrases.
- [x] 2.3 Add order book validation to skip speculative posting when an immediate counter-order exists within the tolerance window.
- [x] 2.4 Update regression scripts/tests or add manual verification notes covering silent acknowledgements and raw predictive messages.

## 3. Validation
- [x] 3.1 Execute manual checks in staging groups to confirm no extra messages appear and speculative orders follow the new format.
- [x] 3.2 Document results in the validation log / admin reports for review.
