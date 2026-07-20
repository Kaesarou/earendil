from abc import ABC, abstractmethod
from typing import Protocol

from app.market.models import MarketSnapshot
from app.market_data.models import MarketDataEvent


class RestMarketDataClient(Protocol):
    def get_market_snapshots(self, symbols: list[str]) -> dict[str, MarketSnapshot]: ...

    def resolve_instrument_ids(self, symbols: list[str]) -> dict[str, int]: ...


class LiveMarketDataFeed(ABC):
    @abstractmethod
    def start(self, symbols: list[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_symbols(self, symbols: list[str]) -> None:
        """Replace the subscribed universe with the supplied symbols."""
        raise NotImplementedError

    @abstractmethod
    def next_event(self, timeout_seconds: float) -> MarketDataEvent | None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def requires_websocket_health(self) -> bool:
        raise NotImplementedError

    def diagnostics(self) -> dict[str, object]:
        return {}
