from datetime import datetime, timedelta, timezone

import pytest

from app.instruments.models import AssetClass
from app.market.models import Candle
from app.market.multi_timeframe import (
    MultiTimeframeCandleEngine,
    MultiTimeframeConfig,
    MultiTimeframeService,
    TimeframeFeatureConfig,
    expected_sampling_quality,
)
from app.market.timeframes import (
    BarCompleteness,
    MultiTimeframeAlignment,
    OpeningRangeStatus,
    SamplingQuality,
    Timeframe,
    TimeframeMaturity,
)
from app.runtime.trading_session_window import TradingSessionDecision

UTC = timezone.utc


def candle_at(
    opened_at: datetime,
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
    symbol: str = 'AAPL',
    sample_count: int = 4,
) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe_seconds=60,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=None,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=1),
        sample_count=sample_count,
    )


def equity_session(start: datetime) -> TradingSessionDecision:
    return TradingSessionDecision(
        asset_class=AssetClass.EQUITY_US,
        session_active=True,
        session_24_7=False,
        collect_snapshots=True,
        new_entries_allowed=True,
        force_close_required=False,
        reason='session_tradable',
        session_start_time=start,
        session_end_time=start + timedelta(hours=6, minutes=30),
        time_until_session_end_minutes=390.0,
        session_key=f'EQUITY_US:{start.isoformat()}',
    )


def small_feature_config() -> TimeframeFeatureConfig:
    return TimeframeFeatureConfig(
        provisional_bars=2,
        ready_bars=4,
        range_lookback_bars=4,
        ema_fast_bars=2,
        ema_slow_bars=4,
        atr_lookback_bars=2,
        compression_lookback_bars=2,
        acceleration_window_bars=1,
    )


def small_config() -> MultiTimeframeConfig:
    return MultiTimeframeConfig(
        feature_configs={
            timeframe.name.lower(): small_feature_config()
            for timeframe in Timeframe
        },
        opening_range_minutes=(3,),
    )


def add_minutes(
    service: MultiTimeframeService,
    session: TradingSessionDecision,
    start: datetime,
    count: int,
    *,
    symbol: str = 'AAPL',
) -> None:
    for minute in range(count):
        close = 100 + minute * 0.1
        service.on_base_candle(
            symbol=symbol,
            candle=candle_at(
                start + timedelta(minutes=minute),
                open_price=close - 0.05,
                high=close + 0.1,
                low=close - 0.1,
                close=close,
                symbol=symbol,
            ),
            session_decision=session,
        )


def test_five_m1_candles_build_one_exact_m5_bar():
    start = datetime(2026, 7, 13, 15, 30, tzinfo=UTC)
    engine = MultiTimeframeCandleEngine('AAPL')
    closed = []
    prices = [100.0, 101.0, 99.0, 103.0, 102.0]

    for minute, price in enumerate(prices):
        update = engine.on_base_candle(
            candle_at(
                start + timedelta(minutes=minute),
                open_price=price,
                high=price + 2,
                low=price - 1,
                close=price + 0.5,
            ),
            session_key='us-session',
            session_start_time=start,
            session_24_7=False,
        )
        closed.extend(update.closed_bars)

    m5 = next(bar for bar in closed if bar.timeframe == Timeframe.M5)
    assert m5.completeness == BarCompleteness.COMPLETE
    assert m5.source_bar_count == 5
    assert m5.expected_source_bar_count == 5
    assert m5.candle.opened_at == start
    assert m5.candle.closed_at == start + timedelta(minutes=5)
    assert m5.candle.open == 100.0
    assert m5.candle.high == 105.0
    assert m5.candle.low == 98.0
    assert m5.candle.close == 102.5
    assert m5.candle.sample_count == 20


def test_missing_m1_is_reported_and_m5_is_incomplete_without_synthetic_bar():
    start = datetime(2026, 7, 13, 15, 30, tzinfo=UTC)
    engine = MultiTimeframeCandleEngine('AAPL')
    updates = []

    for minute in (0, 2, 3, 4):
        updates.append(
            engine.on_base_candle(
                candle_at(
                    start + timedelta(minutes=minute),
                    open_price=100 + minute,
                    high=101 + minute,
                    low=99 + minute,
                    close=100.5 + minute,
                ),
                session_key='us-session',
                session_start_time=start,
                session_24_7=False,
            )
        )

    gaps = [gap for update in updates for gap in update.gaps]
    bars = [bar for update in updates for bar in update.closed_bars]
    m5 = next(bar for bar in bars if bar.timeframe == Timeframe.M5)

    assert len(gaps) == 1
    assert gaps[0].missing_base_candles == 1
    assert m5.completeness == BarCompleteness.INCOMPLETE
    assert m5.source_bar_count == 4
    assert m5.missing_source_bar_count == 1


def test_us_h1_is_anchored_to_session_open_at_half_past():
    start = datetime(2026, 7, 13, 15, 30, tzinfo=UTC)
    engine = MultiTimeframeCandleEngine('AAPL')
    closed = []

    for minute in range(60):
        update = engine.on_base_candle(
            candle_at(
                start + timedelta(minutes=minute),
                open_price=100 + minute / 10,
                high=101 + minute / 10,
                low=99 + minute / 10,
                close=100.5 + minute / 10,
            ),
            session_key='us-session',
            session_start_time=start,
            session_24_7=False,
        )
        closed.extend(update.closed_bars)

    h1 = next(bar for bar in closed if bar.timeframe == Timeframe.H1)
    assert h1.completeness == BarCompleteness.COMPLETE
    assert h1.candle.opened_at == start
    assert h1.candle.closed_at == start + timedelta(hours=1)


def test_maturity_moves_from_unavailable_to_provisional_to_ready():
    start = datetime(2026, 7, 13, 15, 30, tzinfo=UTC)
    session = equity_session(start)
    service = MultiTimeframeService({'AAPL': small_config()})

    add_minutes(service, session, start, 1)
    unavailable = service.build_context(
        symbol='AAPL', side='BUY', as_of=start + timedelta(minutes=1), session_decision=session
    )
    assert unavailable.maturity_by_timeframe['m1'] == TimeframeMaturity.UNAVAILABLE
    assert 'm1' not in unavailable.features_by_timeframe

    add_minutes(service, session, start + timedelta(minutes=1), 1)
    provisional = service.build_context(
        symbol='AAPL', side='BUY', as_of=start + timedelta(minutes=2), session_decision=session
    )
    m1_provisional = provisional.features_by_timeframe['m1']
    assert m1_provisional.maturity == TimeframeMaturity.PROVISIONAL
    assert m1_provisional.atr_percent is None
    assert m1_provisional.compression_ratio is None
    assert provisional.ready_alignment == MultiTimeframeAlignment.UNKNOWN
    assert provisional.alignment_including_provisional == MultiTimeframeAlignment.ALIGNED

    for minute in range(2, 4):
        close = 100 + minute * 0.1
        service.on_base_candle(
            symbol='AAPL',
            candle=candle_at(
                start + timedelta(minutes=minute),
                open_price=close - 0.05,
                high=close + 0.1,
                low=close - 0.1,
                close=close,
            ),
            session_decision=session,
        )
    ready = service.build_context(
        symbol='AAPL', side='BUY', as_of=start + timedelta(minutes=4), session_decision=session
    )
    m1_ready = ready.features_by_timeframe['m1']
    assert m1_ready.maturity == TimeframeMaturity.READY
    assert m1_ready.atr_percent is not None
    assert m1_ready.compression_ratio is not None
    assert ready.ready_alignment == MultiTimeframeAlignment.ALIGNED


def test_default_windows_make_m5_provisional_after_8_bars_and_ready_after_15():
    start = datetime(2026, 7, 13, 15, 30, tzinfo=UTC)
    session = equity_session(start)
    service = MultiTimeframeService()
    add_minutes(service, session, start, 40)

    provisional = service.build_context(
        symbol='AAPL', side='BUY', as_of=start + timedelta(minutes=40), session_decision=session
    )
    assert provisional.maturity_by_timeframe['m5'] == TimeframeMaturity.PROVISIONAL
    assert provisional.features_by_timeframe['m5'].bar_count == 8

    for minute in range(40, 75):
        close = 100 + minute * 0.1
        service.on_base_candle(
            symbol='AAPL',
            candle=candle_at(
                start + timedelta(minutes=minute),
                open_price=close - 0.05,
                high=close + 0.1,
                low=close - 0.1,
                close=close,
            ),
            session_decision=session,
        )
    ready = service.build_context(
        symbol='AAPL', side='BUY', as_of=start + timedelta(minutes=75), session_decision=session
    )
    assert ready.maturity_by_timeframe['m5'] == TimeframeMaturity.READY
    assert ready.features_by_timeframe['m5'].bar_count == 15


def test_features_and_opening_range_are_built_from_closed_bars_only():
    start = datetime(2026, 7, 13, 15, 30, tzinfo=UTC)
    session = equity_session(start)
    service = MultiTimeframeService({'AAPL': small_config()})
    candles = (
        candle_at(start, open_price=100, high=102, low=99, close=101),
        candle_at(start + timedelta(minutes=1), open_price=101, high=104, low=100, close=103),
        candle_at(start + timedelta(minutes=2), open_price=103, high=106, low=102, close=105),
        candle_at(start + timedelta(minutes=3), open_price=105, high=107, low=104, close=106),
    )
    for candle in candles:
        service.on_base_candle(symbol='AAPL', candle=candle, session_decision=session)

    context = service.build_context(
        symbol='AAPL', side='BUY', as_of=start + timedelta(minutes=4), session_decision=session
    )

    m1 = context.features_by_timeframe['m1']
    opening = context.opening_ranges.windows['3']
    assert m1.latest_bar_closed_at == start + timedelta(minutes=4)
    assert m1.range_position_percent == pytest.approx(87.5)
    assert m1.body_percent_of_range == pytest.approx(33.333333)
    assert m1.compression_ratio == pytest.approx(0.75)
    assert opening.status == OpeningRangeStatus.READY
    assert opening.high == 106
    assert opening.low == 99
    assert context.ready_alignment == MultiTimeframeAlignment.ALIGNED


def test_incomplete_opening_range_and_higher_bar_are_not_features():
    start = datetime(2026, 7, 13, 15, 30, tzinfo=UTC)
    session = equity_session(start)
    service = MultiTimeframeService({'AAPL': small_config()})

    for minute in (0, 2, 3, 4):
        service.on_base_candle(
            symbol='AAPL',
            candle=candle_at(
                start + timedelta(minutes=minute),
                open_price=100 + minute,
                high=102 + minute,
                low=99 + minute,
                close=101 + minute,
            ),
            session_decision=session,
        )

    context = service.build_context(
        symbol='AAPL', side='BUY', as_of=start + timedelta(minutes=5), session_decision=session
    )
    all_m5 = service.bars('AAPL', Timeframe.M5)
    complete_m5 = service.bars('AAPL', Timeframe.M5, complete_only=True)

    assert context.opening_ranges.windows['3'].status == OpeningRangeStatus.INCOMPLETE
    assert all_m5[0].completeness == BarCompleteness.INCOMPLETE
    assert complete_m5 == []
    assert context.maturity_by_timeframe['m5'] == TimeframeMaturity.UNAVAILABLE


def test_same_as_of_context_does_not_change_after_future_bars_arrive():
    start = datetime(2026, 7, 13, 15, 30, tzinfo=UTC)
    session = equity_session(start)
    service = MultiTimeframeService({'AAPL': small_config()})

    for minute, close in enumerate((101.0, 102.0, 103.0, 104.0)):
        service.on_base_candle(
            symbol='AAPL',
            candle=candle_at(
                start + timedelta(minutes=minute),
                open_price=close - 0.5,
                high=close + 1,
                low=close - 1,
                close=close,
            ),
            session_decision=session,
        )

    as_of = start + timedelta(minutes=4)
    original = service.build_context(
        symbol='AAPL', side='BUY', as_of=as_of, session_decision=session
    )

    for minute, close in ((4, 90.0), (5, 80.0), (6, 70.0)):
        service.on_base_candle(
            symbol='AAPL',
            candle=candle_at(
                start + timedelta(minutes=minute),
                open_price=close + 1,
                high=close + 2,
                low=close - 1,
                close=close,
            ),
            session_decision=session,
        )

    replayed = service.build_context(
        symbol='AAPL', side='BUY', as_of=as_of, session_decision=session
    )
    assert replayed == original


def test_polling_interval_is_classified_separately_from_fixed_timeframes():
    assert expected_sampling_quality(10) == SamplingQuality.DENSE
    assert expected_sampling_quality(20) == SamplingQuality.ACCEPTABLE
    assert expected_sampling_quality(60) == SamplingQuality.SPARSE
