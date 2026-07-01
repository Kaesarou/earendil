from abc import ABC, abstractmethod

from app.market.models import MarketSnapshot


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
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def close_position(self, position_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_position_open(self, position_id: str) -> bool:
        raise NotImplementedError

    def remember_position_instrument(self, position_id: str, symbol: str) -> None:
        """Optional hook for brokers that must restore local position metadata.

        Some execution brokers, like eToro, need to know the instrument id attached
        to a restored position before they can close it. Generic brokers do not need
        any extra state, so the default implementation is intentionally a no-op.
        """
        return None
