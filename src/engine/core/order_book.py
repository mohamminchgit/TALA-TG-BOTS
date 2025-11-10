from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.common.utils import normalize_persian_numbers

logger = logging.getLogger(__name__)

OrderGroup = str
OrderSide = str


def _parse_int(value: Any) -> Optional[int]:
    """Best-effort conversion of incoming quantity/price values to integers."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        normalized = normalize_persian_numbers(value).replace(",", "").strip()
        if not normalized:
            return None
        try:
            return int(normalized)
        except ValueError:
            logger.debug("Failed to parse integer from value %s", value)
            return None
    return None


def _normalize_alias(alias: Optional[str]) -> str:
    if not alias:
        return ""
    return normalize_persian_numbers(alias).strip().lower()


@dataclass
class OrderEntry:
    message_id: int
    group_label: OrderGroup
    side: OrderSide
    alias: str
    alias_normalized: str
    user_id: Optional[int]
    quantity: int
    remaining_quantity: int
    price: Optional[int]
    posted_at: Optional[str]
    raw_event: Dict[str, Any]
    original_message_id: Optional[int]
    created_at_monotonic: float = field(default_factory=time.monotonic)
    updated_at_monotonic: float = field(default_factory=time.monotonic)

    def apply_fill(self, quantity: int) -> None:
        if quantity <= 0:
            return
        self.remaining_quantity = max(0, self.remaining_quantity - quantity)
        self.updated_at_monotonic = time.monotonic()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "group_label": self.group_label,
            "side": self.side,
            "alias": self.alias,
            "user_id": self.user_id,
            "quantity": self.quantity,
            "remaining_quantity": self.remaining_quantity,
            "price": self.price,
            "posted_at": self.posted_at,
            "created_at_monotonic": self.created_at_monotonic,
            "updated_at_monotonic": self.updated_at_monotonic,
            "original_message_id": self.original_message_id,
        }


class OrderBook:
    """In-memory snapshot of active orders for source and destination groups."""

    _GROUP_KEYS = ("source", "destination")

    def __init__(self) -> None:
        self._orders: Dict[OrderGroup, Dict[int, OrderEntry]] = {group: {} for group in self._GROUP_KEYS}
        self._alias_index: Dict[OrderGroup, Dict[str, set[int]]] = {
            group: defaultdict(set) for group in self._GROUP_KEYS
        }
        self._original_index: Dict[OrderGroup, Dict[int, int]] = {group: {} for group in self._GROUP_KEYS}
        self._advertisements: Dict[int, OrderEntry] = {}

    def apply_event(self, event: Dict[str, Any]) -> None:
        group_label = event.get("group_label")
        if group_label not in self._orders:
            logger.debug("Ignoring event for unknown group %s", group_label)
            return

        category = event.get("category")
        if category in {"buy_order", "sell_order"}:
            entry = self._build_order_entry(event, category)
            if entry:
                self._add_order(entry)
        elif category == "cancel_all":
            self._handle_cancel(group_label, event)
        elif category == "full_match":
            self._handle_full_match(group_label, event)
        elif category == "partial_match":
            self._handle_partial_match(group_label, event)
        elif category == "trade_confirmation":
            self._handle_trade_confirmation(event)
        elif category == "message_deleted":
            self._handle_message_deleted(group_label, event)
        elif category == "auto_advertisement":
            details = event.get("details") or {}
            preferred_side = details.get("side", "sell").lower()
            entry = self._build_order_entry(event, "sell_order" if preferred_side == "sell" else "buy_order")
            if entry:
                self._add_advertisement(entry)
        else:
            logger.debug("Ignoring unsupported event category %s", category)

    def summary(self) -> Dict[str, Any]:
        summary = {}
        for group, orders in self._orders.items():
            buy_count = sum(1 for entry in orders.values() if entry.side == "buy")
            sell_count = sum(1 for entry in orders.values() if entry.side == "sell")
            total_remaining = sum(entry.remaining_quantity for entry in orders.values())
            summary[group] = {
                "orders": len(orders),
                "buy_orders": buy_count,
                "sell_orders": sell_count,
                "total_remaining_quantity": total_remaining,
            }
        summary["advertisements"] = {
            "total": len(self._advertisements),
            "by_side": {
                "buy": sum(1 for entry in self._advertisements.values() if entry.side == "buy"),
                "sell": sum(1 for entry in self._advertisements.values() if entry.side == "sell"),
            },
        }
        return summary

    def snapshot(self) -> Dict[str, Dict[int, Dict[str, Any]]]:
        snapshot = {
            group: {message_id: entry.to_dict() for message_id, entry in orders.items()}
            for group, orders in self._orders.items()
        }
        snapshot["advertisements"] = {message_id: entry.to_dict() for message_id, entry in self._advertisements.items()}
        return snapshot

    def get_entry(self, group_label: OrderGroup, message_id: int) -> Optional[OrderEntry]:
        return self._orders.get(group_label, {}).get(message_id)

    def best_entry(self, group_label: OrderGroup, side: OrderSide) -> Optional[OrderEntry]:
        orders = self._orders.get(group_label)
        if not orders:
            return None

        candidates = [
            entry
            for entry in orders.values()
            if entry.side == side and entry.remaining_quantity > 0 and entry.price is not None
        ]
        if not candidates:
            return None

        if side == "buy":
            return max(candidates, key=lambda e: (e.price, -e.created_at_monotonic))
        if side == "sell":
            return min(candidates, key=lambda e: (e.price, e.created_at_monotonic))
        return None

    def side_entries(self, group_label: OrderGroup, side: OrderSide) -> List[OrderEntry]:
        orders = self._orders.get(group_label)
        if not orders:
            return []

        candidates = [
            entry
            for entry in orders.values()
            if entry.side == side and entry.remaining_quantity > 0 and entry.price is not None
        ]
        if side == "buy":
            candidates.sort(key=lambda e: (-int(e.price), e.created_at_monotonic))
        else:
            candidates.sort(key=lambda e: (int(e.price), e.created_at_monotonic))
        return candidates

    def reserve_quantity(self, group_label: OrderGroup, message_id: int, quantity: int) -> int:
        if quantity <= 0:
            return 0

        entry = self._orders.get(group_label, {}).get(message_id)
        if not entry or entry.remaining_quantity <= 0:
            return 0

        reserved = min(quantity, entry.remaining_quantity)
        entry.apply_fill(reserved)

        if entry.remaining_quantity <= 0:
            self._remove_order(group_label, message_id)

        logger.info(
            "Reserved %s units from order %s (%s %s)",
            reserved,
            message_id,
            group_label,
            entry.side,
        )
        return reserved

    def purge_stale(self, max_age_seconds: int) -> int:
        if max_age_seconds <= 0:
            return 0

        now = time.monotonic()
        removed = 0
        for group in self._GROUP_KEYS:
            message_ids = [
                message_id
                for message_id, entry in list(self._orders[group].items())
                if now - entry.updated_at_monotonic >= max_age_seconds
            ]
            for message_id in message_ids:
                self._remove_order(group, message_id)
                removed += 1

        if removed:
            logger.info("Purged %s stale orders exceeding %s seconds", removed, max_age_seconds)
        return removed

    def _build_order_entry(self, event: Dict[str, Any], category: str) -> Optional[OrderEntry]:
        message = event.get("message") or {}
        message_id = message.get("id")
        if message_id is None:
            logger.debug("Skipping order event without message id: %s", event)
            return None

        details = event.get("details") or {}
        sender = event.get("sender") or {}

        alias = details.get("alias") or sender.get("display_name") or sender.get("username") or "Unknown"
        alias = alias.strip()
        alias_normalized = _normalize_alias(alias)

        quantity = _parse_int(details.get("quantity")) or 0
        price = _parse_int(details.get("price"))

        entry = OrderEntry(
            message_id=message_id,
            group_label=event.get("group_label", "unknown"),
            side="buy" if category == "buy_order" else "sell",
            alias=alias,
            alias_normalized=alias_normalized,
            user_id=sender.get("id"),
            quantity=quantity,
            remaining_quantity=quantity,
            price=price,
            posted_at=message.get("date"),
            raw_event=event,
            original_message_id=message.get("reply_to"),
        )
        logger.info(
            "Registered %s order %s (%s %s @ %s)",
            event.get("group_label"),
            message_id,
            alias,
            quantity,
            price,
        )
        return entry

    def _add_order(self, entry: OrderEntry) -> None:
        if entry.message_id in self._orders[entry.group_label]:
            self._remove_order(entry.group_label, entry.message_id)

        self._orders[entry.group_label][entry.message_id] = entry
        self._alias_index[entry.group_label][entry.alias_normalized].add(entry.message_id)
        if entry.original_message_id is not None:
            self._original_index[entry.group_label][int(entry.original_message_id)] = entry.message_id

    def _remove_order(self, group_label: OrderGroup, message_id: int) -> Optional[OrderEntry]:
        entry = self._orders[group_label].pop(message_id, None)
        if not entry:
            return None

        alias_ids = self._alias_index[group_label].get(entry.alias_normalized)
        if alias_ids is not None:
            alias_ids.discard(message_id)
            if not alias_ids:
                self._alias_index[group_label].pop(entry.alias_normalized, None)
        if entry.original_message_id is not None:
            stored_message_id = self._original_index[group_label].get(int(entry.original_message_id))
            if stored_message_id == message_id:
                self._original_index[group_label].pop(int(entry.original_message_id), None)

        logger.info("Removed order %s from %s", message_id, group_label)
        return entry

    def _remove_advertisement_by_id(self, message_id: int) -> Optional[OrderEntry]:
        entry = self._advertisements.pop(message_id, None)
        if entry:
            logger.info("Removed advertisement %s", message_id)
        return entry

    def _remove_advertisements_by_alias(self, alias_normalized: str) -> List[int]:
        removed: List[int] = []
        for message_id, entry in list(self._advertisements.items()):
            if entry.alias_normalized == alias_normalized:
                self._remove_advertisement_by_id(message_id)
                removed.append(message_id)
        return removed

    def _add_advertisement(self, entry: OrderEntry) -> None:
        self._advertisements[entry.message_id] = entry
        logger.info(
            "Registered advertisement %s (%s %s @ %s)",
            entry.message_id,
            entry.alias,
            entry.quantity,
            entry.price,
        )

    def pop_advertisement(self, message_id: int) -> Optional[OrderEntry]:
        return self._advertisements.pop(message_id, None)

    def advertisements(self, side: Optional[OrderSide] = None) -> List[OrderEntry]:
        entries = list(self._advertisements.values())
        if side is None:
            return entries
        return [entry for entry in entries if entry.side == side]

    def supervisor_message_id_for_original(self, group_label: OrderGroup, original_message_id: int) -> Optional[int]:
        return self._original_index.get(group_label, {}).get(original_message_id)

    def _remove_orders_by_alias(self, group_label: OrderGroup, alias_normalized: str) -> List[int]:
        message_ids = list(self._alias_index[group_label].get(alias_normalized, set()))
        for message_id in message_ids:
            self._remove_order(group_label, message_id)
        return message_ids

    def _handle_cancel(self, group_label: OrderGroup, event: Dict[str, Any]) -> None:
        message = event.get("message") or {}
        reply_to = message.get("reply_to")
        details = event.get("details") or {}
        sender = event.get("sender") or {}

        alias = details.get("alias") or sender.get("display_name") or sender.get("username") or ""
        alias_normalized = details.get("alias_normalized") or _normalize_alias(alias)

        removed_ids: List[int] = []
        if reply_to is not None:
            entry = self._remove_order(group_label, reply_to)
            if entry:
                removed_ids.append(reply_to)
            try:
                reply_id = int(reply_to)
            except (TypeError, ValueError):
                reply_id = None
            if reply_id is not None and self._remove_advertisement_by_id(reply_id):
                removed_ids.append(reply_to)

        if alias_normalized:
            removed_ids.extend(self._remove_orders_by_alias(group_label, alias_normalized))
            removed_ids.extend(self._remove_advertisements_by_alias(alias_normalized))

        if removed_ids:
            logger.info(
                "Cancelled %s orders in %s for alias %s",
                len(set(removed_ids)),
                group_label,
                alias or "<unknown>",
            )
        else:
            logger.info(
                "No matching orders found to cancel in %s for alias %s (reply_to=%s)",
                group_label,
                alias or "<unknown>",
                reply_to,
            )

    def _handle_full_match(self, group_label: OrderGroup, event: Dict[str, Any]) -> None:
        reference_id = (event.get("message") or {}).get("reply_to")
        if reference_id is None:
            return
        self._remove_order(group_label, reference_id)

    def _handle_partial_match(self, group_label: OrderGroup, event: Dict[str, Any]) -> None:
        reference_id = (event.get("message") or {}).get("reply_to")
        if reference_id is None:
            return

        fill_quantity = _parse_int((event.get("details") or {}).get("quantity"))
        if not fill_quantity:
            return

        entry = self._orders[group_label].get(reference_id)
        if not entry:
            return

        entry.apply_fill(fill_quantity)
        if entry.remaining_quantity <= 0:
            self._remove_order(group_label, reference_id)
        else:
            logger.info(
                "Order %s in %s partially matched; remaining quantity %s",
                reference_id,
                group_label,
                entry.remaining_quantity,
            )

    def _handle_trade_confirmation(self, event: Dict[str, Any]) -> None:
        details = event.get("details") or {}
        aliases = [details.get("buyer"), details.get("seller")]
        aliases = [alias for alias in aliases if alias]
        if not aliases:
            return

        removed_total = 0
        for alias in aliases:
            alias_norm = _normalize_alias(alias)
            for group in self._GROUP_KEYS:
                removed_ids = self._remove_orders_by_alias(group, alias_norm)
                removed_total += len(removed_ids)
            removed_ads = self._remove_advertisements_by_alias(alias_norm)
            removed_total += len(removed_ads)

        if removed_total:
            logger.info(
                "Cleared %s orders in response to trade confirmation (buyer=%s, seller=%s)",
                removed_total,
                details.get("buyer"),
                details.get("seller"),
            )

    def _handle_message_deleted(self, group_label: OrderGroup, event: Dict[str, Any]) -> None:
        details = event.get("details") or {}
        message_ids: set[int] = set()
        explicit = details.get("message_ids") or []
        for value in explicit:
            try:
                message_ids.add(int(value))
            except (TypeError, ValueError):
                logger.debug("Skipping non-integer deleted message id: %s", value)

        message = event.get("message") or {}
        message_id = message.get("id")
        if message_id is not None:
            message_ids.add(int(message_id))

        if not message_ids:
            return

        removed = 0
        for target_id in message_ids:
            if self._remove_order(group_label, target_id):
                removed += 1
            else:
                self._remove_advertisement_by_id(target_id)

        if removed:
            logger.info("Removed %s orders from %s due to message deletion", removed, group_label)