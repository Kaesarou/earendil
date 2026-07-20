from datetime import datetime, timezone

from app.brokers.base import BrokerClient, OpenPositionResult
from app.market.models import MarketSnapshot
from app.runtime.broker_queries import (
    UnknownOrderLookup,
    get_fresh_position_open_states,
    resolve_unknown_open_order,
)


class PortfolioBroker(BrokerClient):
    def __init__(self):
        self.portfolio_calls = 0
        self.order_calls = 0

    def get_portfolio(self):
        self.portfolio_calls += 1
        return {
            'clientPortfolio': {
                'positions': [
                    {'positionID': 'p-1', 'isOpen': True},
                    {'positionID': 'p-2', 'isOpen': False},
                ]
            }
        }

    def get_order_details(self, order_id: str):
        self.order_calls += 1
        return {
            'status': {'id': 1, 'name': 'Executed', 'errorCode': 0},
            'positionExecutions': [
                {
                    'positionId': 'p-new',
                    'openingData': {'avgPrice': 101.5},
                }
            ],
        }

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        raise NotImplementedError

    def get_market_snapshots(self, symbols: list[str]):
        raise NotImplementedError

    def get_account_equity(self) -> float:
        return 1000.0

    def open_position(self, symbol, side, amount, stop_loss, take_profit):
        return OpenPositionResult(position_id='unused')

    def close_position(self, position_id: str) -> None:
        return None

    def is_position_open(self, position_id: str) -> bool:
        raise AssertionError('individual position lookup must not be used')


def test_fresh_position_states_use_one_portfolio_snapshot():
    broker = PortfolioBroker()

    states = get_fresh_position_open_states(broker, ['p-1', 'p-2', 'p-3'])

    assert states == {'p-1': True, 'p-2': False, 'p-3': False}
    assert broker.portfolio_calls == 1


def test_unknown_order_recovers_from_order_lookup_before_portfolio():
    broker = PortfolioBroker()
    lookup = UnknownOrderLookup(
        order_id='o-1',
        reference_id='r-1',
        symbol='BTC',
        side='BUY',
        amount=100.0,
        submitted_at=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
    )

    resolution = resolve_unknown_open_order(broker, lookup)

    assert resolution.status == 'confirmed'
    assert resolution.matched_by == 'order_lookup'
    assert resolution.result == OpenPositionResult(
        position_id='p-new',
        executed_entry_price=101.5,
    )
    assert broker.order_calls == 1
    assert broker.portfolio_calls == 0
