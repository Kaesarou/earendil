from app.brokers.etoro.etoro_client import EtoroClient
from app.market.models import MarketSnapshot


class EtoroRestMarketDataClient:
    def __init__(self, client: EtoroClient) -> None:
        self.client = client

    def get_market_snapshots(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        return self.client.get_market_snapshots(symbols)

    def resolve_instrument_ids(self, symbols: list[str]) -> dict[str, int]:
        normalized = list(
            dict.fromkeys(symbol.strip().upper() for symbol in symbols)
        )
        return {
            symbol: self.client._find_instrument_id(symbol)
            for symbol in normalized
        }
