from datetime import datetime, timedelta, timezone

from app.market.models import MarketSnapshot
from app.market_data.coordinator import MarketDataCoordinator
from app.market_data.models import (
    MarketDataEvent,
    MarketDataSource,
    SymbolFeedState,
)


BASE_TIME = datetime(2026, 7, 21, 20, 0, tzinfo=timezone.utc)


def _event(at: datetime, message_id: str) -> MarketDataEvent:
    return MarketDataEvent(
        symbol='BTC',
        source=MarketDataSource.WEBSOCKET,
        received_at=at,
        snapshot=MarketSnapshot(
            symbol='BTC',
            bid=100.0,
            ask=100.1,
            last=100.05,
            timestamp=at,
            received_at=at,
        ),
        message_id=message_id,
        connection_id='connection-1',
    )


def _coordinator() -> MarketDataCoordinator:
    coordinator = MarketDataCoordinator(
        websocket_required=True,
        symbol_silence_seconds=15.0,
    )
    coordinator.initialize_symbols(['BTC'], now=BASE_TIME)
    return coordinator


def test_entry_is_blocked_when_symbol_becomes_silent_without_open_position():
    coordinator = _coordinator()
    coordinator.decision_for(_event(BASE_TIME + timedelta(seconds=1), '1'))

    assert coordinator.entry_allowed(
        'BTC',
        now=BASE_TIME + timedelta(seconds=15),
    ) is True
    assert coordinator.entry_allowed(
        'BTC',
        now=BASE_TIME + timedelta(seconds=17),
    ) is False
    assert coordinator.state_for('BTC') == SymbolFeedState.WS_STALE
    assert coordinator.metrics['symbol_stale_count'] == 1


def test_event_after_silence_requires_two_coherent_updates_before_entry():
    coordinator = _coordinator()
    coordinator.decision_for(_event(BASE_TIME + timedelta(seconds=1), '1'))

    first = coordinator.decision_for(
        _event(BASE_TIME + timedelta(seconds=20), '2')
    )
    assert first.entry_allowed is False
    assert coordinator.state_for('BTC') == SymbolFeedState.RECOVERING

    second = coordinator.decision_for(
        _event(BASE_TIME + timedelta(seconds=21), '3')
    )
    assert second.entry_allowed is True
    assert coordinator.state_for('BTC') == SymbolFeedState.WS_HEALTHY
    assert coordinator.metrics['symbol_recovery_count'] == 1
