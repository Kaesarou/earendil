from datetime import datetime, timezone

from app.market.candle_builder import CandleBuilder
from app.market.models import MarketSnapshot
from app.market.timeframes import BASE_TIMEFRAME


def snapshot_at(value: float, timestamp: str) -> MarketSnapshot:
    return MarketSnapshot(
        symbol='BTC',
        bid=value - 1,
        ask=value + 1,
        last=value,
        timestamp=datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc),
    )


def test_candle_builder_uses_fixed_m1_default():
    builder = CandleBuilder()

    assert builder.timeframe_seconds == BASE_TIMEFRAME.value == 60


def test_candle_builder_returns_none_until_bucket_changes():
    builder = CandleBuilder()

    result = builder.on_snapshot(
        snapshot_at(100.0, '2026-06-22T17:10:10')
    )

    assert result is None


def test_candle_builder_closes_candle_when_minute_changes():
    builder = CandleBuilder()

    builder.on_snapshot(snapshot_at(100.0, '2026-06-22T17:10:10'))
    builder.on_snapshot(snapshot_at(105.0, '2026-06-22T17:10:20'))
    builder.on_snapshot(snapshot_at(98.0, '2026-06-22T17:10:30'))

    candle = builder.on_snapshot(
        snapshot_at(102.0, '2026-06-22T17:11:01')
    )

    assert candle is not None
    assert candle.symbol == 'BTC'
    assert candle.timeframe_seconds == 60
    assert candle.open == 100.0
    assert candle.high == 105.0
    assert candle.low == 98.0
    assert candle.close == 98.0
    assert candle.volume is None
    assert candle.sample_count == 3
    assert candle.opened_at == datetime(2026, 6, 22, 17, 10, tzinfo=timezone.utc)
    assert candle.closed_at == datetime(2026, 6, 22, 17, 11, tzinfo=timezone.utc)


def test_candle_builder_preserves_exact_close_when_next_snapshot_has_a_gap():
    builder = CandleBuilder()

    builder.on_snapshot(snapshot_at(100.0, '2026-06-22T17:10:10'))
    candle = builder.on_snapshot(snapshot_at(110.0, '2026-06-22T17:15:05'))

    assert candle is not None
    assert candle.opened_at == datetime(2026, 6, 22, 17, 10, tzinfo=timezone.utc)
    assert candle.closed_at == datetime(2026, 6, 22, 17, 11, tzinfo=timezone.utc)
    assert candle.sample_count == 1


def test_candle_builder_starts_new_bucket_after_closing_previous_one():
    builder = CandleBuilder()

    builder.on_snapshot(snapshot_at(100.0, '2026-06-22T17:10:10'))
    candle = builder.on_snapshot(snapshot_at(110.0, '2026-06-22T17:11:05'))

    assert candle is not None
    assert candle.close == 100.0

    next_candle = builder.on_snapshot(snapshot_at(120.0, '2026-06-22T17:12:01'))

    assert next_candle is not None
    assert next_candle.open == 110.0
    assert next_candle.close == 110.0


def test_candle_builder_reset_drops_current_bucket():
    builder = CandleBuilder()

    builder.on_snapshot(snapshot_at(100.0, '2026-06-22T17:10:10'))
    builder.reset()
    candle = builder.on_snapshot(snapshot_at(110.0, '2026-06-22T17:11:05'))

    assert candle is None
