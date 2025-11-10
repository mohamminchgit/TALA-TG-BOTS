from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from telethon import events

from src.common.constants import (
    MARKET_PRICE_PATTERN,
    ORDER_BUY_PATTERN,
    ORDER_SELL_PATTERN,
    TRADE_CONFIRMATION_PATTERN,
)
from src.common.utils import normalize_persian_numbers
def _extract_alias_from_order_message(text: str) -> Optional[str]:
    if not text:
        return None
    match = ORDER_BUY_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    match = ORDER_SELL_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return None

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from src.bot_agent.agent import BotAgent


@dataclass
class ClassifiedMessage:
    category: str
    original_text: str
    normalized_text: str
    details: Optional[dict] = None


def classify_message(text: str) -> ClassifiedMessage:
    original = text or ""
    normalized = normalize_persian_numbers(original)
    stripped = normalized.replace(" ", "").lower()

    if "آگهیخودکار" in stripped or "آگهی خودکار" in normalized:
        lines = [line.strip() for line in original.splitlines() if line.strip()]
        order_line = None
        for line in lines:
            if ORDER_BUY_PATTERN.search(line) or ORDER_SELL_PATTERN.search(line):
                order_line = line
                break
        details = {"advertisement": True}
        if order_line:
            buy_match = ORDER_BUY_PATTERN.search(order_line)
            sell_match = ORDER_SELL_PATTERN.search(order_line) if not buy_match else None
            match = buy_match or sell_match
            if match:
                alias, quantity, price = match.groups()
                side = "buy" if buy_match else "sell"
                details.update(
                    {
                        "side": side,
                        "alias": alias.strip(),
                        "quantity": normalize_persian_numbers(quantity),
                        "price": normalize_persian_numbers(price).replace(",", ""),
                    }
                )
        return ClassifiedMessage("auto_advertisement", original, normalized, details)

    buy_match = ORDER_BUY_PATTERN.search(original)
    if buy_match:
        alias, quantity, price = buy_match.groups()
        details = {
            "side": "buy",
            "alias": alias.strip(),
            "quantity": normalize_persian_numbers(quantity),
            "price": normalize_persian_numbers(price).replace(",", ""),
        }
        return ClassifiedMessage("buy_order", original, normalized, details)

    sell_match = ORDER_SELL_PATTERN.search(original)
    if sell_match:
        alias, quantity, price = sell_match.groups()
        details = {
            "side": "sell",
            "alias": alias.strip(),
            "quantity": normalize_persian_numbers(quantity),
            "price": normalize_persian_numbers(price).replace(",", ""),
        }
        return ClassifiedMessage("sell_order", original, normalized, details)
    if stripped == "ن":
        return ClassifiedMessage("cancel_all", original, normalized)
    if stripped == "ب":
        return ClassifiedMessage("full_match", original, normalized)
    if stripped.isdigit():
        return ClassifiedMessage("partial_match", original, normalized, {"quantity": stripped})
    market_match = MARKET_PRICE_PATTERN.search(original)
    if market_match:
        price = market_match.group(1)
        details = {"price": normalize_persian_numbers(price).replace(",", "")}
        return ClassifiedMessage("market_price", original, normalized, details)

    confirmation_match = TRADE_CONFIRMATION_PATTERN.search(original)
    if confirmation_match:
        buyer = confirmation_match.group("buyer").strip()
        seller = confirmation_match.group("seller").strip()
        quantity = normalize_persian_numbers(confirmation_match.group("quantity"))
        raw_price = confirmation_match.group("price")
        price = normalize_persian_numbers(raw_price).replace(",", "")
        reference = confirmation_match.groupdict().get("reference")
        reference_normalized = normalize_persian_numbers(reference) if reference else None

        details = {
            "buyer": buyer,
            "seller": seller,
            "quantity": quantity,
            "price": price,
            "raw_price": raw_price,
        }
        if reference_normalized:
            details["reference"] = reference_normalized
            details["trade_id"] = reference_normalized

        return ClassifiedMessage("trade_confirmation", original, normalized, details)
    if stripped in {"ping", "!ping", "status", "!status"}:
        return ClassifiedMessage("ping", original, normalized)

    return ClassifiedMessage("unknown", original, normalized)


async def handle_group_message(agent: "BotAgent", event: events.NewMessage.Event) -> None:
    if event.out:
        return

    message_text = event.raw_text or ""
    classification = classify_message(message_text)
    chat_id = event.chat_id
    sender = await event.get_sender()
    sender_name = getattr(sender, "first_name", None) or getattr(sender, "username", "Unknown")

    if classification.category == "cancel_all":
        details = dict(classification.details or {})
        reply_to = getattr(event.message, "reply_to_msg_id", None) if event.message else None
        details["mode"] = "reply" if reply_to is not None else "standalone"
        alias_hint: Optional[str] = None
        if reply_to is not None:
            try:
                reply_message = await event.get_reply_message()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Failed to fetch reply message for cancellation: %s", exc)
                reply_message = None
            if reply_message and reply_message.raw_text:
                alias_hint = _extract_alias_from_order_message(reply_message.raw_text)
                if alias_hint:
                    details["reply_text"] = reply_message.raw_text
        if not alias_hint:
            alias_hint = getattr(sender, "first_name", None) or getattr(sender, "username", None)
        if alias_hint:
            alias_normalized = normalize_persian_numbers(alias_hint).strip()
            if alias_normalized:
                details.setdefault("alias", alias_hint.strip())
                details.setdefault("alias_normalized", alias_normalized.lower())
        classification.details = details

    logger.info(
        "%s observed %s message from %s in chat %s: %s",
        agent.alias,
        classification.category,
        sender_name,
        chat_id,
        message_text,
    )

    await agent.process_classified_message(event, classification)

    if classification.category == "ping" and agent.config.ack_messages:
        logger.info("Ping received in chat %s; responding silently", chat_id)
