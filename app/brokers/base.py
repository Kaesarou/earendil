from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.market.models import MarketSnapshot


@dataclass(frozen=True)
class OpenPositionResult:
    position_id: str
    executed_entry_price: float | None = None


@dataclass(frozen=True)
class ClosePositionSubmission:
    position_id: str
    close_order_id: str | None
    reference_id: str | None
    submitted_at: datetime
    accepted_at: datetime
    broker_response: dict[str, Any]


class BrokerClient(ABC):
    @abstractmethod
    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        raise NotImplementedError

    @abstractmethod
    def get_market_snapshots(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        raise NotImplementedError

    @abstractmethod
    def get_account_equity(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def open_position(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_loss: float,
        take_profit: float,
    ) -> OpenPositionResult:
        raise NotImplementedError

    @abstractmethod
    def close_position(self, position_id: str) -> ClosePositionSubmission:
        """Submit one close request and return as soon as the broker accepts it.

        Portfolio disappearance is confirmed asynchronously by the runtime. This
        method must never poll the portfolio for closure confirmation.
        """
        raise NotImplementedError

    @abstractmethod
    def is_position_open(self, position_id: str) -> bool:
        raise NotImplementedError

    def remember_position_instrument(self, position_id: str, symbol: str) -> None:
        """Restore broker-specific metadata needed to manage a position."""
        return None
