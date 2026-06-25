from app.brokers.base import BrokerClient
from app.market.models import MarketSnapshot


class MarketDataService:
    def __init__(self, broker: BrokerClient):
        self.broker = broker

    def snapshot(self, symbol: str) -> MarketSnapshot:
        return self.get_snapshot(symbol)

    def get_snapshot(self, symbol: str) -> MarketSnapshot:
        return self.broker.get_market_snapshot(symbol)