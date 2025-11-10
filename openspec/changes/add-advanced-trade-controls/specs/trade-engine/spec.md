## ADDED Requirements
### Requirement: Fixed-Delta Spread Matching
The engine SHALL evaluate every observed order using a configurable fixed price delta to guarantee buy-low/sell-high behaviour before creating new market posts.

#### Scenario: Buyer-first opportunity
- **GIVEN** the source group reports a buy order `🔵 سلطان 1 خ 45400`
- **AND** `FIXED_SPREAD_DELTA` is configured to 10 (default)
- **WHEN** the destination order book contains a sell order priced at or below 45390
- **THEN** the engine SHALL reserve the cheapest qualifying sell order(s) totalling at most the configured carry limit and reply immediately instead of posting a new order.

#### Scenario: Buyer-first bridging order
- **GIVEN** the source group reports a buy order `🔵 سلطان 1 خ 45400`
- **AND** no qualifying sell order exists in the destination order book
- **WHEN** the engine evaluates the opportunity
- **THEN** it SHALL post a buy order in the destination group for the matching quantity using price `45400 - FIXED_SPREAD_DELTA`, encoded with the existing trader-text suffix format.

#### Scenario: Buyer-first round trip completion
- **GIVEN** the engine posted a destination buy order at `45400 - FIXED_SPREAD_DELTA`
- **AND** the trading supervisor confirms the fill against a destination seller
- **THEN** the engine SHALL immediately reply in the source group to fulfil the original buyer’s demand, using the quantity actually filled and respecting the configured carry limits.

#### Scenario: Seller-first opportunity
- **GIVEN** the source group reports a sell order `🔴 امین 1 ف 45390`
- **AND** the destination order book contains a buy order priced at or above 45400
- **THEN** the engine SHALL reserve the best-priced destination buys (up to the carry limit) and reply to execute the trade without issuing new posts.

#### Scenario: Seller-first bridging order
- **GIVEN** the source group reports a sell order `🔴 امین 1 ف 45390`
- **AND** no qualifying buy order exists in the destination order book
- **WHEN** the engine evaluates the opportunity
- **THEN** it SHALL post a sell order in the destination group for price `45390 + FIXED_SPREAD_DELTA`, encoded with the trader-text suffix format.

#### Scenario: Seller-first round trip completion
- **GIVEN** the engine posted a destination sell order at `45390 + FIXED_SPREAD_DELTA`
- **AND** the trading supervisor confirms the fill against a destination buyer
- **THEN** the engine SHALL immediately reply in the source group to satisfy the original seller’s intent, using the filled quantity and honouring the carry limits.

### Requirement: Auto-Advertisement Opportunity Handling
The engine SHALL treat messages classified as auto advertisements as watch-list inventory and never post speculative orders against them until profitable counterparties exist.

#### Scenario: Monitor advertisement until counterparty exists
- **GIVEN** an incoming message is tagged `آگهی خودکار`
- **WHEN** no counterparty within the fixed delta is detected
- **THEN** the engine SHALL record the advertisement internally without posting any order or command.

#### Scenario: Execute against qualifying counterparty
- **GIVEN** an advertisement `آگهی خودکار` for `🔴 پروین 1 ف 45475`
- **AND** the destination group presents a buy order `🔵 امین 1 خ 45500`
- **THEN** the engine SHALL treat the advertisement like a seller-first opportunity, honouring the fixed delta and carry limits when executing the trade.

### Requirement: Carry Limit Controls
The engine SHALL obey configurable quantity caps when reserving or posting orders, with a distinct limit for opportunistic fills.

#### Scenario: Enforce base carry limit
- **GIVEN** `BASE_CARRY_LIMIT` is set to 1
- **WHEN** the engine evaluates an order requiring more quantity than the base cap
- **THEN** it SHALL only reserve or post up to one unit and record the remaining demand for future opportunities.

#### Scenario: Opportunistic override
- **GIVEN** `OPPORTUNITY_CARRY_LIMIT` is configured to 3
- **AND** an auto advertisement represents three available units with matching counterparties
- **THEN** the engine MAY reserve or post up to three units for that specific opportunity while keeping regular flows capped by `BASE_CARRY_LIMIT`.
