from datetime import datetime, timedelta, timezone

from app.instruments.models import AssetClass
from app.market.models import Candle
from app.market.multi_timeframe import MultiTimeframeConfig
from app.market.session_timeframe_service import FullSessionMultiTimeframeService
from app.market.timeframes import OpeningRangeStatus, Timeframe
from app.runtime.trading_session_window import TradingSessionDecision


def test_opening_range_remains_available_after_more_than_four_hours():
    start = datetime(2026, 7, 13, 15, 30, tzinfo=timezone.utc)
    session = TradingSessionDecision(
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
        session_key='us-session',
    )
    config = MultiTimeframeConfig(
        range_lookback_bars=3,
        ema_fast_bars=2,
        ema_slow_bars=3,
        atr_lookback_bars=2,
        compression_lookback_bars=2,
        acceleration_window_bars=1,
        opening_range_minutes=(15,),
    )
    service = FullSessionMultiTimeframeService({'AAPL': config})

    for minute in range(301):
        opened_at = start + timedelta(minutes=minute)
        price = 100 + minute / 100
        service.on_base_candle(
            symbol='AAPL',
            candle=Candle(
                symbol='AAPL',
                timeframe_seconds=60,
                open=price,
                high=price + 1,
                low=price - 1,
                close=price + 0.2,
                volume=None,
                opened_at=opened_at,
                closed_at=opened_at + timedelta(minutes=1),
                sample_count=4,
            ),
            session_decision=session,
        )

    context = service.build_context(
        symbol='AAPL',
        side='BUY',
        as_of=start + timedelta(minutes=301),
        session_decision=session,
    )

    assert len(service.bars('AAPL', Timeframe.M1)) == 301
    assert context.opening_ranges.windows['15'].status == OpeningRangeStatus.READY
    assert context.opening_ranges.windows['15'].source_bar_count == 15
