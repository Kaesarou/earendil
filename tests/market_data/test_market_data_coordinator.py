from datetime import datetime, timedelta, timezone

from app.market.models import MarketSnapshot
from app.market_data.coordinator import MarketDataCoordinator
from app.market_data.models import MarketDataEvent, MarketDataSource, SymbolFeedState


NOW = datetime(2026, 7, 20, 0, 0, tzinfo=timezone.utc)


def event(
    *,
    timestamp=NOW,
    source=MarketDataSource.WEBSOCKET,
    message_id='m1',
    connection_id='c1',
):
    return MarketDataEvent(
        symbol='BTC',
        source=source,
        received_at=timestamp,
        snapshot=MarketSnapshot(
            symbol='BTC',
            bid=99.0,
            ask=101.0,
            last=100.0,
            timestamp=timestamp,
        ),
        message_id=message_id,
        connection_id=connection_id,
    )


def coordinator():
    value = MarketDataCoordinator(
        websocket_required=True,
        symbol_silence_seconds=15,
    )
    value.initialize_symbols(['BTC'], now=NOW)
    return value


def test_accepting_websocket_event_makes_symbol_healthy():
    value = coordinator()
    assert value.precheck(event()).accepted is True
    decision = value.mark_accepted(event())
    assert decision.entry_allowed is True
    assert value.state_for('BTC') == SymbolFeedState.WS_HEALTHY


def test_duplicate_message_id_is_scoped_by_connection():
    value = coordinator()
    first = event()
    assert value.precheck(first).accepted is True
    value.mark_accepted(first)

    assert value.precheck(first).reason == 'duplicate_message_id'
    assert value.precheck(event(connection_id='c2')).accepted is True


def test_quiet_symbol_only_enters_fallback_when_explicitly_checked_as_position():
    value = coordinator()
    first = event()
    value.precheck(first)
    value.mark_accepted(first)

    assert value.position_fallback_symbols(
        symbols=[],
        now=NOW + timedelta(seconds=30),
    ) == []
    assert value.state_for('BTC') == SymbolFeedState.WS_HEALTHY

    assert value.position_fallback_symbols(
        symbols=['BTC'],
        now=NOW + timedelta(seconds=30),
    ) == ['BTC']
    assert value.state_for('BTC') == SymbolFeedState.REST_FALLBACK


def test_fallback_blocks_entries_until_two_coherent_websocket_events():
    value = coordinator()
    first = event()
    value.precheck(first)
    value.mark_accepted(first)
    value.position_fallback_symbols(
        symbols=['BTC'],
        now=NOW + timedelta(seconds=30),
    )

    recovery_one = event(
        timestamp=NOW + timedelta(seconds=31),
        message_id='m2',
    )
    value.precheck(recovery_one)
    assert value.mark_accepted(recovery_one).entry_allowed is False

    recovery_two = event(
        timestamp=NOW + timedelta(seconds=32),
        message_id='m3',
    )
    value.precheck(recovery_two)
    assert value.mark_accepted(recovery_two).entry_allowed is True


def test_rest_fallback_snapshot_cannot_advance_websocket_watermark():
    value = coordinator()
    first = event(timestamp=NOW + timedelta(seconds=2))
    value.precheck(first)
    value.mark_accepted(first)

    fallback = event(
        timestamp=NOW + timedelta(seconds=20),
        source=MarketDataSource.REST_FALLBACK,
        message_id=None,
        connection_id=None,
    )
    assert value.precheck(fallback).reason == 'rest_fallback_position_only'

    websocket_after_fallback = event(
        timestamp=NOW + timedelta(seconds=3),
        message_id='m2',
    )
    assert value.precheck(websocket_after_fallback).accepted is True


def test_strictly_older_websocket_timestamp_is_rejected():
    value = coordinator()
    first = event(timestamp=NOW + timedelta(seconds=2))
    value.precheck(first)
    value.mark_accepted(first)
    older = event(timestamp=NOW, message_id='m2')
    assert value.precheck(older).reason == 'strict_out_of_order_timestamp'
