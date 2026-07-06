from app.brokers.base import BrokerClient, OpenPositionResult
from app.execution.trade_executor import TradeExecutor
from app.market.models import MarketSnapshot
from app.risk.models import TradePlan


class FakeBroker(BrokerClient):
    def __init__(self):
        self.payload = None

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        raise NotImplementedError

    def get_market_snapshots(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        raise NotImplementedError

    def get_account_equity(self) -> float:
        raise NotImplementedError

    def open_position(self, symbol: str, side: str, amount: float, stop_loss: float, take_profit: float):
        self.payload = (symbol, side, amount, stop_loss, take_profit)
        return OpenPositionResult(position_id='p1', executed_entry_price=238.0)

    def close_position(self, position_id: str) -> None:
        return None

    def is_position_open(self, position_id: str) -> bool:
        return True


def test_executor_returns_result_object():
    broker = FakeBroker()
    result = TradeExecutor(broker).execute(
        TradePlan(approved=True, reason='test', symbol='AAPL', side='BUY', amount=100.0, stop_loss=99.0, take_profit=102.0)
    )

    assert result == OpenPositionResult(position_id='p1', executed_entry_price=238.0)
    assert broker.payload == ('AAPL', 'BUY', 100.0, 99.0, 102.0)


def test_executor_returns_none_for_rejected_plan():
    broker = FakeBroker()
    result = TradeExecutor(broker).execute(TradePlan(approved=False, reason='rejected'))

    assert result is None
    assert broker.payload is None
