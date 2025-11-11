from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set


@dataclass
class TradeContext:
    trade_id: str
    source_message_id: int
    destination_message_id: int
    quantity: int
    source_price: int
    destination_price: int
    spread: int
    strategy: str
    expected_agents: Set[str] = field(default_factory=lambda: {"source", "destination"})
    created_at: float = field(default_factory=time.time)
    completed_agents: set[str] = field(default_factory=set)
    last_status: Optional[str] = None
    failed: bool = False
    failure_status: Optional[str] = None
    agent_status: Dict[str, str] = field(default_factory=dict)
    agent_details: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    agent_actions: Dict[str, Optional[str]] = field(default_factory=dict)
    pending_destination_legs: set[str] = field(default_factory=set)
    destination_message_ids: Dict[str, int] = field(default_factory=dict)
    destination_leg_quantities: Dict[str, int] = field(default_factory=dict)
    destination_leg_prices: Dict[str, int] = field(default_factory=dict)
    supervisor_message_ids: Dict[str, int] = field(default_factory=dict)


class TradeTracker:
    """Tracks trade contexts from match time until execution completes."""

    def __init__(self) -> None:
        self._records: Dict[str, TradeContext] = {}

    @staticmethod
    def _is_success_status(status: str) -> bool:
        return status in {"success", "confirmation_detected"}

    @staticmethod
    def _is_failure_status(status: str) -> bool:
        return status in {
            "error",
            "rpc_error",
            "flood_wait",
            "confirmation_timeout",
            "timeout",
            "failed",
            "cancelled",
        }

    def register(self, context: TradeContext) -> None:
        self._records[context.trade_id] = context

    def get(self, trade_id: str) -> Optional[TradeContext]:
        return self._records.get(trade_id)

    def pop(self, trade_id: str) -> Optional[TradeContext]:
        return self._records.pop(trade_id, None)

    def discard(self, trade_id: str) -> None:
        self._records.pop(trade_id, None)

    def record_result(
        self,
        trade_id: str,
        agent: Optional[str],
        status: str,
        details: Optional[Dict[str, Any]] = None,
        action: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[TradeContext]:
        context = self._records.get(trade_id)
        if context is None:
            return None

        agent_key = agent
        if metadata and metadata.get("agent_key"):
            agent_key = str(metadata["agent_key"])

        context.last_status = status
        if agent_key:
            context.agent_status[agent_key] = status
            context.agent_details[agent_key] = details or {}
            context.agent_actions[agent_key] = action

            confirmation_id: Optional[int] = None
            if details and "confirmation_message_id" in details:
                try:
                    confirmation_id = int(details["confirmation_message_id"])
                except (TypeError, ValueError):
                    confirmation_id = None
            if confirmation_id is not None:
                context.supervisor_message_ids[agent_key] = confirmation_id
                if agent_key.startswith("destination_leg_"):
                    context.supervisor_message_ids.setdefault("destination", confirmation_id)
                elif agent_key.startswith("source"):
                    context.supervisor_message_ids["source"] = confirmation_id
                elif agent_key == "destination":
                    context.supervisor_message_ids["destination"] = confirmation_id

        if agent_key in context.pending_destination_legs:
            if self._is_failure_status(status):
                context.failed = True
                if context.failure_status is None:
                    context.failure_status = status
                context.pending_destination_legs.discard(agent_key)
                context.completed_agents.add(agent_key)
                context.agent_status["destination"] = status
                context.agent_details["destination"] = details or {}
                context.agent_actions["destination"] = action
                context.completed_agents.add("destination")
                return context

            if self._is_success_status(status):
                if metadata and "leg_quantity" in metadata:
                    context.destination_leg_quantities[agent_key] = int(metadata["leg_quantity"])
                if metadata and "leg_price" in metadata:
                    context.destination_leg_prices[agent_key] = int(metadata["leg_price"])
                if metadata and "leg_message_id" in metadata:
                    context.destination_message_ids[agent_key] = int(metadata["leg_message_id"])
                context.pending_destination_legs.discard(agent_key)
                context.completed_agents.add(agent_key)
                if context.pending_destination_legs:
                    return None
                context.agent_status["destination"] = status
                context.agent_details["destination"] = details or {}
                context.agent_actions["destination"] = action
                agent = "destination"
                agent_key = "destination"
            else:
                return None

        if self._is_success_status(status) and agent_key:
            context.completed_agents.add(agent_key)
            if context.completed_agents >= context.expected_agents:
                return context
            return None

        if self._is_failure_status(status):
            context.failed = True
            if context.failure_status is None:
                context.failure_status = status
            if agent_key:
                context.completed_agents.add(agent_key)
            return context

        return None

    def add_expected_agent(self, trade_id: str, agent: str) -> None:
        context = self._records.get(trade_id)
        if context is None:
            return
        context.expected_agents.add(agent)

    def register_destination_leg(
        self,
        trade_id: str,
        agent_key: str,
        message_id: int,
        *,
        quantity: int,
        price: int,
    ) -> None:
        context = self._records.get(trade_id)
        if context is None:
            return
        context.expected_agents.add("destination")
        context.pending_destination_legs.add(agent_key)
        context.destination_message_ids[agent_key] = message_id
        context.destination_leg_quantities[agent_key] = max(0, quantity)
        context.destination_leg_prices[agent_key] = max(0, price)
        if not context.destination_message_id:
            context.destination_message_id = message_id

    def update_destination_message(self, trade_id: str, message_id: int, agent_key: Optional[str] = None) -> None:
        context = self._records.get(trade_id)
        if context is None:
            return
        if agent_key:
            context.destination_message_ids[agent_key] = message_id
            if not context.destination_message_id:
                context.destination_message_id = message_id
            return
        context.destination_message_id = message_id
        context.destination_message_ids["destination"] = message_id

    def update_destination_price(self, trade_id: str, price: int) -> None:
        context = self._records.get(trade_id)
        if context is None:
            return
        context.destination_price = price

    def get_agent_status(self, trade_id: str, agent: str) -> Optional[str]:
        context = self._records.get(trade_id)
        if context is None:
            return None
        return context.agent_status.get(agent)

    def get_agent_details(self, trade_id: str, agent: str) -> Dict[str, Any]:
        context = self._records.get(trade_id)
        if context is None:
            return {}
        return context.agent_details.get(agent, {})

    def set_supervisor_message_id(self, trade_id: str, agent: str, message_id: int) -> None:
        context = self._records.get(trade_id)
        if context is None:
            return
        try:
            message_id_int = int(message_id)
        except (TypeError, ValueError):
            return
        context.supervisor_message_ids[agent] = message_id_int
        if agent.startswith("destination"):
            context.supervisor_message_ids["destination"] = message_id_int
        elif agent.startswith("source"):
            context.supervisor_message_ids["source"] = message_id_int

    def get_supervisor_message_id(self, trade_id: str, agent: str, *, fallback: bool = True) -> Optional[int]:
        context = self._records.get(trade_id)
        if context is None:
            return None
        if agent in context.supervisor_message_ids:
            return context.supervisor_message_ids[agent]
        if not fallback:
            return None
        if agent.startswith("destination_leg_"):
            return context.supervisor_message_ids.get("destination")
        if agent.startswith("destination"):
            return context.supervisor_message_ids.get("destination")
        if agent.startswith("source"):
            return context.supervisor_message_ids.get("source")
        return None
