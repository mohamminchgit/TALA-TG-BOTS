from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

TradeDirection = Literal["source_sell", "source_buy"]


@dataclass
class PolicySnapshot:
    fixed_spread_delta: int
    base_carry_limit: int
    opportunity_carry_limit: int  # 0 represents unlimited


class TradePolicy:
    """Encapsulate spread and carry-limit rules for the trade engine."""

    def __init__(self, *, fixed_spread_delta: int, base_carry_limit: int, opportunity_carry_limit: int) -> None:
        self._fixed_spread_delta = max(0, fixed_spread_delta)
        self._base_carry_limit = max(1, base_carry_limit)
        self._opportunity_carry_limit = opportunity_carry_limit if opportunity_carry_limit >= 0 else self._base_carry_limit

    @property
    def snapshot(self) -> PolicySnapshot:
        return PolicySnapshot(
            fixed_spread_delta=self._fixed_spread_delta,
            base_carry_limit=self._base_carry_limit,
            opportunity_carry_limit=self._opportunity_carry_limit,
        )

    def update(
        self,
        *,
        fixed_spread_delta: Optional[int] = None,
        base_carry_limit: Optional[int] = None,
        opportunity_carry_limit: Optional[int] = None,
    ) -> PolicySnapshot:
        if fixed_spread_delta is not None:
            self._fixed_spread_delta = max(0, fixed_spread_delta)
        if base_carry_limit is not None:
            self._base_carry_limit = max(1, base_carry_limit)
        if opportunity_carry_limit is not None:
            if opportunity_carry_limit < 0:
                opportunity_carry_limit = self._base_carry_limit
            self._opportunity_carry_limit = opportunity_carry_limit
        return self.snapshot

    def is_profitable(self, direction: TradeDirection, *, source_price: int, counter_price: int) -> bool:
        """Return True when the fixed spread requirement is satisfied."""
        if direction == "source_sell":
            return (counter_price - source_price) >= self._fixed_spread_delta
        return (source_price - counter_price) >= self._fixed_spread_delta

    def target_destination_price(self, direction: TradeDirection, *, source_price: int) -> int:
        """Derive the bridging post price for speculative orders."""
        if direction == "source_sell":
            return source_price + self._fixed_spread_delta
        return source_price - self._fixed_spread_delta

    def allowed_quantity(self, requested: int, *, opportunistic: bool = False) -> int:
        if requested <= 0:
            return 0
        limit = self._opportunity_carry_limit if opportunistic else self._base_carry_limit
        if limit == 0:  # unlimited
            return requested
        return min(limit, requested)

    def remaining_capacity(self, already_committed: int, *, opportunistic: bool = False) -> int:
        limit = self._opportunity_carry_limit if opportunistic else self._base_carry_limit
        if limit == 0:
            return 0
        remaining = limit - already_committed
        return remaining if remaining > 0 else 0