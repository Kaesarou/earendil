from types import SimpleNamespace

from app.runtime.market_data_runtime import EventDrivenMarketRuntime


class FakeFeed:
    requires_websocket_health = True

    def __init__(self) -> None:
        self.started_symbols: list[str] = []
        self.stopped = False

    def start(self, symbols: list[str]) -> None:
        self.started_symbols = list(symbols)

    def update_symbols(self, symbols: list[str]) -> None:
        self.started_symbols = list(symbols)

    def subscribed_symbols(self) -> tuple[str, ...]:
        return tuple(self.started_symbols)

    def next_event(self, timeout_seconds: float):
        raise KeyboardInterrupt

    def stop(self) -> None:
        self.stopped = True

    def diagnostics(self):
        return {'subscribed_symbols': self.started_symbols}


class FakeCoordinator:
    def __init__(self) -> None:
        self.metrics = {}
        self.initialized_symbols: list[str] = []

    def initialize_symbols(self, symbols: list[str], *, now) -> None:
        self.initialized_symbols = list(symbols)

    def snapshot(self):
        return {}


class FakeJournal:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def write(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


class SessionAwareRuntime(EventDrivenMarketRuntime):
    def __init__(self) -> None:
        self.run_id = 'test-run'
        self.settings = SimpleNamespace(
            rest_control_interval_seconds=60.0,
            ws_symbol_silence_seconds=5.0,
        )
        self.live_market_data = FakeFeed()
        self.coordinator = FakeCoordinator()
        self.trade_journal = FakeJournal()
        self.position_tracker = SimpleNamespace(
            open_positions_snapshot=lambda: []
        )
        self.heartbeat = SimpleNamespace(maybe_emit=lambda **kwargs: None)
        self.active_symbols: list[str] = []
        self.context_asset_classes = {}
        self.loop_id = 0
        self._last_session_refresh = 0.0
        self._last_rest_control = 0.0
        self._last_position_reconciliation = 0.0
        self._feed_started = False
        self._subscribed_symbols: tuple[str, ...] = ()
        self._applied_feed_symbols: tuple[str, ...] = ()

    def _refresh_sessions_if_due(self, now, monotonic_now: float) -> None:
        self.active_symbols = ['AIR.PA']
        self.context_asset_classes = {'FRA40': object()}

    def _refresh_applied_market_data_subscription(self, now) -> None:
        return None

    def _reconcile_positions_if_due(self, now, monotonic_now: float) -> None:
        return None


def test_runtime_starts_feed_with_only_current_session_symbols():
    runtime = SessionAwareRuntime()

    assert runtime.run() == 'stopped'
    assert runtime.live_market_data.started_symbols == ['AIR.PA', 'FRA40']
    assert 'AAPL' not in runtime.live_market_data.started_symbols
    assert runtime.coordinator.initialized_symbols == ['AIR.PA', 'FRA40']
    assert runtime.live_market_data.stopped is True
