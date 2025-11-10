from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class EngineState:
    """Runtime flags controlling trading mode and circuit breakers."""

    monitor_only: bool = False
    paused_until_epoch: float = 0.0
    shutdown_requested: bool = False

    def can_trade(self) -> bool:
        if self.monitor_only:
            return False
        return time.time() >= self.paused_until_epoch

    def set_monitor_only(self, enabled: bool) -> None:
        self.monitor_only = enabled

    def pause_for(self, seconds: float) -> None:
        seconds = max(0.0, seconds)
        self.paused_until_epoch = max(self.paused_until_epoch, time.time() + seconds)

    def resume(self) -> None:
        self.paused_until_epoch = 0.0
        self.monitor_only = False

    def request_shutdown(self) -> None:
        self.shutdown_requested = True
