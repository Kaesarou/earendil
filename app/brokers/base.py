from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.market.models import MarketSnapshot


@dataclass(frozen=True)
class OpenPositionResult:
    position_id: str
    executed_entry_price: float | None = None


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
    def close_position(self, position_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_position_open(self, position_id: str) -> bool:
        raise NotImplementedError

    def get_position_open_states(
        self,
        position_ids: list[str],
    ) -> dict[str, bool]:
        """Return broker open/closed state for each requested position.

        Brokers with a portfolio endpoint should override this method so one
        portfolio snapshot can answer every position lookup. The default keeps
        existing broker implementations compatible.
        """
        return {
            position_id: self.is_position_open(position_id)
            for position_id in position_ids
        }

    def remember_position_instrument(self, position_id: str, symbol: str) -> None:
        """Optional hook for brokers that must restore local position metadata.

        Some execution brokers, like eToro, need to know the instrument id attached
        to a restored position before they can close it. Generic brokers do not need
        any extra state, so the default implementation is intentionally a no-op.
        """
        return None
