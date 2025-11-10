# Change: Improve cancellation handling for mirrored orders

## Why
- Traders cancel source-group orders by replying "ن" to the supervisor's confirmation message or by posting a standalone "ن". Today the engine sometimes keeps destination-side bait orders alive even after the source order disappears, triggering unnecessary fills and locked capital.
- Destination bait created by the predictive strategy must be withdrawn immediately when the corresponding source order is cancelled, filled by someone else, or expires after roughly 60 seconds. The current implementation does not consistently clear those positions.
- We have no explicit spec coverage for cancellation workflows, so behaviour is ambiguous and regressions are hard to catch.

## What Changes
- Add explicit requirements for how agents detect "ن" messages (reply vs. standalone) and publish cancellation events.
- Define engine behaviour to revoke any pending destination exposure when the source order cancels, is fulfilled by someone else, or times out after 60 seconds.
- Ensure the engine clears speculative bait orders and removes reserved counterparties when the source opportunity disappears.

## Impact
- Affects `telegram-agent` capability (event classification for Persian "ن" cancellation patterns).
- Affects `trade-engine` capability (state machine for bait orders and cancellation response).
- Requires updates to risk manager / predictive market maker to enforce 60 second expiry and cancellation propagation.

## Out of Scope
- Switching to alternate storage for order state.
- Handling admin-driven cancellations or panic commands (already covered elsewhere).
- Extending behaviour to admin bot UI (will simply reflect engine state after implementation).

