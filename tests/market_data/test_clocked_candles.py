from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.market.models import Candle, MarketSnapshot
from app.market.session_timeframe_service import FullSessionMultiTimeframeService
from app.market.timeframes import BarCompleteness, Timeframe
from app.market_data.candle_stream import QualityAwareCandleBuilder
from app.market_data.models import MarketDataEvent, MarketDataSource


def snapshot(timestamp: datetime, last: float = 100.0) -> MarketSnapshot:
    return MarketSnapshot(
        symbol='BTC',
        bid=last - 0.1,
        ask=last + 0.1,
        last=last,
        timestamp=timestamp,
        received_at=timestamp,
    )


def websocket_event(timestamp: datetime, last: float = 100.0) -> MarketDataEvent:
    return MarketDataEvent(
        symbol='BTC',
        source=MarketDataSource.WEBSOCKET,
        received_at=timestamp,
        snapshot=snapshot(timestamp, last),
        message_id=f'm-{timestamp.timestamp()}',
        connection_id='c-1',
        price_changed=True,
    )


def test_clock_closes_quiet_m1_and_carries_price_without_fake_samples():
    start = datetime(2026, 7, 20, 12, 0, 5, tzinfo=timezone.utc)
    builder = QualityAwareCandleBuilder()
    builder.on_event(websocket_event(start))

    first = builder.finalize_until(
        datetime(2026, 7, 20, 12, 1, 1, tzinfo=timezone.utc),
        grace_seconds=1,
        max_carry_forward_age_seconds=180,
    )
    assert len(first) == 1
    assert first[0].candle.opened_at == start.replace(second=0)
    assert first[0].candle.closed_at == start.replace(second=0) + timedelta(minutes=1)
    assert first[0].candle.sample_count == 1
    assert not first[0].quality.carried_forward

    carried = builder.finalize_until(
        datetime(2026, 7, 20, 12, 2, 1, tzinfo=timezone.utc),
        grace_seconds=1,
        max_carry_forward_age_seconds=180,
    )
    assert len(carried) == 1
    assert carried[0].candle.sample_count == 0
    assert carried[0].quality.carried_forward
    assert carried[0].candle.open == carried[0].candle.close == 100.0
    assert not carried[0].quality.degraded


def test_stale_carried_price_degrades_but_single_ordering_drop_does_not():
    start = datetime(2026, 7, 20, 12, 0, 5, tzinfo=timezone.utc)
    builder = QualityAwareCandleBuilder(
        ordering_drop_degrade_count=3,
        ordering_drop_degrade_ratio=0.10,
    )
    builder.on_event(websocket_event(start))
    builder.record_out_of_order_drop()

    first = builder.finalize_until(
        datetime(2026, 7, 20, 12, 1, 1, tzinfo=timezone.utc),
        grace_seconds=1,
        max_carry_forward_age_seconds=180,
    )[0]
    assert first.quality.out_of_order_drop_count == 1
    assert not first.quality.degraded

    late = builder.finalize_until(
        datetime(2026, 7, 20, 12, 5, 1, tzinfo=timezone.utc),
        grace_seconds=1,
        max_carry_forward_age_seconds=180,
    )
    assert any(item.quality.degraded for item in late)
    assert any(
        'stale_carried_forward_price' in item.quality.degraded_reasons
        for item in late
    )


def test_ordering_drop_rate_requires_count_and_ratio_thresholds():
    start = datetime(2026, 7, 20, 12, 0, 5, tzinfo=timezone.utc)
    builder = QualityAwareCandleBuilder(
        ordering_drop_degrade_count=3,
        ordering_drop_degrade_ratio=0.10,
    )
    builder.on_event(websocket_event(start))
    for _ in range(3):
        builder.record_out_of_order_drop()

    result = builder.finalize_until(
        datetime(2026, 7, 20, 12, 1, 1, tzinfo=timezone.utc),
        grace_seconds=1,
        max_carry_forward_age_seconds=180,
    )[0]

    assert result.quality.degraded
    assert 'ordering_drop_rate' in result.quality.degraded_reasons


def test_degraded_m1_makes_clocked_m5_incomplete():
    service = FullSessionMultiTimeframeService()
    session = SimpleNamespace(
        session_key='crypto-2026-07-20',
        session_start_time=None,
        session_24_7=True,
    )
    start = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    final_update = None
    for minute in range(5):
        candle = Candle(
            symbol='BTC',
            timeframe_seconds=60,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0 + minute,
            volume=None,
            opened_at=start + timedelta(minutes=minute),
            closed_at=start + timedelta(minutes=minute + 1),
            sample_count=1,
            carried_forward=minute == 3,
            source_price_age_seconds=200.0 if minute == 3 else 0.0,
            quality_degraded=minute == 3,
        )
        final_update = service.on_base_candle(
            symbol='BTC',
            candle=candle,
            session_decision=session,
        )

    m5 = [
        bar
        for bar in final_update.closed_bars
        if bar.timeframe == Timeframe.M5
    ]
    assert len(m5) == 1
    assert m5[0].completeness == BarCompleteness.INCOMPLETE
    assert m5[0].candle.carried_forward
    assert m5[0].candle.quality_degraded
