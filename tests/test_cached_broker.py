from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.brokers.base import BrokerClient
from app.brokers.cached_broker import CachedBrokerClient
from app.market.models import MarketSnapshot


@dataclass
class CountingBroker(BrokerClient):
    snapshot_calls: int = 0
    batch_snapshot_calls: int = 0
    equity_calls: int = 0
    position_status_calls: int = 0
    open_calls: int = 0
    close_calls: int = 0
    positions: dict[str, bool] = field(default_factory=dict)

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        self.snapshot_calls += 1
        return MarketSnapshot(
            symbol=symbol,
            bid=99.0 + self.snapshot_calls,
            ask=101.0 + self.snapshot_calls,
            last=100.0 + self.snapshot_calls,
            timestamp=datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc),
        )

    def get_market_snapshots(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        self.batch_snapshot_calls += 1
        return {
            symbol: MarketSnapshot(
                symbol=symbol,
                bid=99.0 + index,
                ask=101.0 + index,
                last=100.0 + index,
                timestamp=datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc),
            )
            for index, symbol in enumerate(symbols, start=1)
        }

    def get_account_equity(self) -> float:
        self.equity_calls += 1
        return 1000.0 + self.equity_calls

    def open_position(self, symbol: str, side: str, amount: float, stop_loss: float, take_profit: float) -> str:
        self.open_calls += 1
        position_id = f'position-{self.open_calls}'
        self.positions[position_id] = True
        return position_id

    def close_position(self, position_id: str) -> None:
        self.close_calls += 1
        self.positions[position_id] = False

    def is_position_open(self, position_id: str) -> bool:
        self.position_status_calls += 1
        return self.positions.get(position_id, False)


@dataclass
class EtoroSearchBroker(CountingBroker):
    captured_search_params: dict | None = None

    def _get(self, path: str, params: dict | None = None) -> dict:
        if path != '/api/v1/market-data/search':
            raise AssertionError(f'Unexpected path={path}')

        self.captured_search_params = params
        return {
            'items': [
                {
                    'internalSymbolFull': 'BTC',
                    'internalInstrumentDisplayName': 'Bitcoin',
                    'instrumentId': 100000,
                    'cvtBid': 99.0,
                    'cvtAsk': 101.0,
                    'currentRate': 100.0,
                },
                {
                    'internalSymbolFull': 'ETH',
                    'internalInstrumentDisplayName': 'Ethereum',
                    'instrumentId': 100001,
                    'cvtBid': 199.0,
                    'cvtAsk': 201.0,
                    'currentRate': 200.0,
                },
            ]
        }

    def _extract_items(self, payload: dict) -> list[dict]:
        value = payload.get('items')
        if isinstance(value, list):
            return value
        return []


def test_cached_broker_caches_market_snapshots_by_symbol():
    delegate = CountingBroker()
    broker = CachedBrokerClient(delegate=delegate, market_snapshot_ttl_seconds=60.0)

    first_snapshot = broker.get_market_snapshot('btc')
    second_snapshot = broker.get_market_snapshot(' BTC ')

    assert first_snapshot == second_snapshot
    assert delegate.batch_snapshot_calls == 1


def test_cached_broker_batches_missing_market_snapshots():
    delegate = CountingBroker()
    broker = CachedBrokerClient(delegate=delegate, market_snapshot_ttl_seconds=60.0)

    snapshots = broker.get_market_snapshots(['BTC', 'ETH', 'DOGE'])

    assert list(snapshots) == ['BTC', 'ETH', 'DOGE']
    assert delegate.batch_snapshot_calls == 1
    assert delegate.snapshot_calls == 0


def test_cached_broker_batches_only_uncached_market_snapshots():
    delegate = CountingBroker()
    broker = CachedBrokerClient(delegate=delegate, market_snapshot_ttl_seconds=60.0)

    broker.get_market_snapshots(['BTC', 'ETH'])
    broker.get_market_snapshots(['BTC', 'ETH', 'DOGE'])

    assert delegate.batch_snapshot_calls == 2
    assert delegate.snapshot_calls == 0
    assert 'DOGE' in broker.market_snapshot_cache


def test_etoro_batch_market_snapshots_use_search_market_data():
    delegate = EtoroSearchBroker()
    broker = CachedBrokerClient(delegate=delegate, market_snapshot_ttl_seconds=60.0)

    snapshots = broker.get_market_snapshots(['BTC', 'ETH'])

    assert list(snapshots) == ['BTC', 'ETH']
    assert delegate.captured_search_params == {'internalSymbolFull': 'BTC,ETH'}
    assert snapshots['BTC'].bid == 99.0
    assert snapshots['BTC'].ask == 101.0
    assert snapshots['BTC'].last == 100.0
    assert snapshots['ETH'].bid == 199.0
    assert snapshots['ETH'].ask == 201.0
    assert snapshots['ETH'].last == 200.0


def test_cached_broker_caches_account_equity():
    delegate = CountingBroker()
    broker = CachedBrokerClient(delegate=delegate, account_equity_ttl_seconds=60.0)

    first_equity = broker.get_account_equity()
    second_equity = broker.get_account_equity()

    assert first_equity == second_equity
    assert delegate.equity_calls == 1


def test_cached_broker_caches_position_status():
    delegate = CountingBroker(positions={'position-1': True})
    broker = CachedBrokerClient(delegate=delegate, position_status_ttl_seconds=60.0)

    assert broker.is_position_open('position-1') is True
    assert broker.is_position_open('position-1') is True
    assert delegate.position_status_calls == 1


def test_cached_broker_invalidates_account_and_position_cache_after_open():
    delegate = CountingBroker(positions={'position-1': True})
    broker = CachedBrokerClient(
        delegate=delegate,
        account_equity_ttl_seconds=60.0,
        position_status_ttl_seconds=60.0,
    )

    broker.get_account_equity()
    broker.is_position_open('position-1')

    broker.open_position('BTC', 'BUY', 10.0, 99.0, 105.0)

    broker.get_account_equity()
    broker.is_position_open('position-1')

    assert delegate.equity_calls == 2
    assert delegate.position_status_calls == 2


def test_cached_broker_does_not_cache_when_ttl_is_disabled():
    delegate = CountingBroker()
    broker = CachedBrokerClient(
        delegate=delegate,
        market_snapshot_ttl_seconds=0.0,
        account_equity_ttl_seconds=0.0,
        batch_market_rates_enabled=False,
    )

    broker.get_market_snapshot('BTC')
    broker.get_market_snapshot('BTC')
    broker.get_account_equity()
    broker.get_account_equity()

    assert delegate.snapshot_calls == 2
    assert delegate.equity_calls == 2
