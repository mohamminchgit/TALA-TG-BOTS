from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TradeRecord:
    trade_id: str
    strategy: str
    quantity: int
    source_price: float
    destination_price: float
    profit: float
    status: str
    executed_at: datetime
    source_message_id: Optional[int] = None
    destination_message_id: Optional[int] = None
