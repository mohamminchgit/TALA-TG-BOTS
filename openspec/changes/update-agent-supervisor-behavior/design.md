## Context
Live Telegram trading groups rely on a human supervisor that rewrites raw trader inputs. Our current automation leaks its presence by posting acknowledgement messages in the source group and by emitting supervisor-formatted speculative orders in the destination group. The deployment target requires the bots to behave like silent traders whose messages the supervisor later reformats.

## Goals / Non-Goals
- Goals: keep agents silent except for true trading actions, ensure speculative orders look like raw trader input, prevent redundant speculative posts when an executable counter-order already exists.
- Non-Goals: redesign risk management, alter admin controls, or change existing confirmation parsing rules.

## Decisions
- **Silent acknowledgements**: Strip chat-facing acknowledgement strings from source agent command handlers; retain structured logging and Redis reporting for observability.
- **Raw predictive text**: Extend predictive market maker to build messages in `[quantity][side][price_suffix]` form using Persian digits preference while allowing configuration for side mapping (`خ` for buy, `ف` for sell`). Humans (supervisor) reformat after the bot posts.
- **Pre-flight validation**: Before issuing a speculative `post_new_order`, re-run the spread evaluation to confirm no qualifying counter order exists and that the order book has not changed since detection. Abort if a matching opportunity appears, preventing extra noise.

## Risks / Trade-offs
- Removing acknowledgements reduces immediate visual feedback; mitigated by admin reports and manual tests.
- Raw text may conflict with localization expectations; we will reuse existing normalization utilities to convert digits appropriately.

## Open Questions
- None identified; behaviour aligns with the shared trading supervisor guidelines.
