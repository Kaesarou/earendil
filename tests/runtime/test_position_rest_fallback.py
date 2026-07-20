from datetime import datetime, timezone
from types import SimpleNamespace

from app.runtime.market_data_maintenance import MarketDataMaintenance


NOW = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)


class FakeFeed:
    requires_websocket_health = True

    def connection_healthy(self) -> bool:
        return True


class FakeCoordinator:
    def position_fallback_symbols(self, *, symbols, now, force=False):
        return list(symbols)


class FakeBrokerOperations:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], datetime]] = []

    def schedule_position_fallback(
        self,
        *,
        symbols: list[str],
        now: datetime,
    ) -> bool:
        self.calls.append((list(symbols), now))
        return True


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
        self.broker_operations = FakeBrokerOperations()


def test_no_open_position_means_no_rest_fallback_task():
    runtime = RuntimeState([])

    runtime._run_position_fallback_if_due(NOW, 20.0)

    assert runtime.broker_operations.calls == []


def test_all_stale_positions_share_one_fixed_cadence_batch():
    runtime = RuntimeState(['AIR.PA', 'BNP.PA'])

    runtime._run_position_fallback_if_due(NOW, 20.0)
    runtime._run_position_fallback_if_due(NOW, 25.0)
    runtime._run_position_fallback_if_due(NOW, 30.0)

    assert runtime.broker_operations.calls == [
        (['AIR.PA', 'BNP.PA'], NOW),
        (['AIR.PA', 'BNP.PA'], NOW),
    ]


def test_position_fallback_only_schedules_position_lifecycle_work():
    runtime = RuntimeState(['AIR.PA'])

    runtime._run_position_fallback_if_due(NOW, 20.0)

    assert runtime.broker_operations.calls == [(['AIR.PA'], NOW)]
    assert not hasattr(runtime, '_handle_event')
