from datetime import datetime, timezone
from types import SimpleNamespace

from app.market.models import MarketSnapshot
from app.runtime.market_data_maintenance import MarketDataMaintenance


NOW = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)


class FakeFeed:
    requires_websocket_health = True

    def connection_healthy(self) -> bool:
        return True


class FakeRestMarketData:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def get_market_snapshots(self, symbols: list[str]):
        self.calls.append(list(symbols))
        return {
            symbol: MarketSnapshot(
                symbol=symbol,
                bid=99.0,
                ask=101.0,
                last=100.0,
                timestamp=NOW,
            )
            for symbol in symbols
        }


class FakeCoordinator:
    def __init__(self) -> None:
        self.failed: list[list[str]] = []
        self.succeeded: list[list[str]] = []

    def position_fallback_symbols(self, *, symbols, now, force=False):
        return list(symbols)

    def mark_fallback_failed(self, symbols):
        self.failed.append(list(symbols))

    def mark_fallback_succeeded(self, symbols):
        self.succeeded.append(list(symbols))


class FakeJournal:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def write(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


class RuntimeState(MarketDataMaintenance):
    def __init__(self, symbols: list[str]) -> None:
        self.live_market_data = FakeFeed()
        self.position_tracker = SimpleNamespace(
            open_positions_snapshot=lambda: [
                SimpleNamespace(symbol=symbol) for symbol in symbols
            ]
        )
        self._applied_feed_symbols = tuple(symbols)
        self._last_position_fallback = 0.0
        self.settings = SimpleNamespace(
            position_fallback_interval_seconds=10.0
        )
        self.coordinator = FakeCoordinator()
        self.rest_market_data = FakeRestMarketData()
        self.trade_journal = FakeJournal()
        self.executor = object()
        self.risk_manager = object()
        self.position_store = object()
        self.cooldown_store = object()
        self.is_broker_authorization_error = lambda exc: False
        self.loop_id = 1


def test_no_open_position_means_no_rest_fallback(monkeypatch):
    runtime = RuntimeState([])
    monkeypatch.setattr(
        'app.runtime.market_data_maintenance.close_positions_triggered_by_snapshot',
        lambda **kwargs: None,
    )

    runtime._run_position_fallback_if_due(NOW, 20.0)

    assert runtime.rest_market_data.calls == []


def test_all_stale_positions_share_one_fixed_cadence_batch(monkeypatch):
    runtime = RuntimeState(['AIR.PA', 'BNP.PA'])
    processed: list[str] = []
    monkeypatch.setattr(
        'app.runtime.market_data_maintenance.close_positions_triggered_by_snapshot',
        lambda **kwargs: processed.append(kwargs['symbol']),
    )

    runtime._run_position_fallback_if_due(NOW, 20.0)
    runtime._run_position_fallback_if_due(NOW, 25.0)
    runtime._run_position_fallback_if_due(NOW, 30.0)

    assert runtime.rest_market_data.calls == [
        ['AIR.PA', 'BNP.PA'],
        ['AIR.PA', 'BNP.PA'],
    ]
    assert processed == ['AIR.PA', 'BNP.PA', 'AIR.PA', 'BNP.PA']


def test_position_fallback_does_not_enter_market_event_pipeline(monkeypatch):
    runtime = RuntimeState(['AIR.PA'])
    processed: list[str] = []
    monkeypatch.setattr(
        'app.runtime.market_data_maintenance.close_positions_triggered_by_snapshot',
        lambda **kwargs: processed.append(kwargs['symbol']),
    )

    runtime._run_position_fallback_if_due(NOW, 20.0)

    assert processed == ['AIR.PA']
    assert [event for event, _ in runtime.trade_journal.events] == [
        'rest_position_fallback_snapshot'
    ]
