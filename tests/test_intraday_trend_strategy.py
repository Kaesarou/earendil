from datetime import datetime, timedelta, timezone

import pytest

from app.market.models import Candle
from app.strategies.intraday_trend import (
    IntradayTrendStrategy,
    IntradayTrendStrategyConfig,
)


def candle(
    open: float,
    close: float,
    high: float | None = None,
    low: float | None = None,
    opened_at: datetime | None = None,
) -> Candle:
    opened_at = opened_at or datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    closed_at = opened_at + timedelta(minutes=1)

    high = high if high is not None else max(open, close)
    low = low if low is not None else min(open, close)

    return Candle(
        symbol='AAPL',
        timeframe_seconds=60,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=None,
        opened_at=opened_at,
        closed_at=closed_at,
    )


def config(allow_short: bool = True) -> IntradayTrendStrategyConfig:
    return IntradayTrendStrategyConfig(
        lookback=3,
        fast_lookback=3,
        slow_lookback=5,
        session_lookback=5,
        min_session_move_percent=0.1,
        min_breakout_percent=0.01,
        min_candle_range_percent=0.01,
        min_close_position_percent=70.0,
        allow_short=allow_short,
        atr_lookback=5,
    )


def test_intraday_trend_emits_buy_when_session_and_breakout_are_bullish():
    strategy = IntradayTrendStrategy(config())

    strategy.on_candle(candle(open=100.0, close=100.0, high=100.1, low=99.8))
    strategy.on_candle(candle(open=101.0, close=101.0, high=101.1, low=100.8))
    strategy.on_candle(candle(open=102.0, close=102.0, high=102.1, low=101.8))
    strategy.on_candle(candle(open=103.0, close=103.0, high=103.1, low=102.8))
    strategy.on_candle(candle(open=104.0, close=104.0, high=104.1, low=103.8))

    signal = strategy.on_candle(
        candle(
            open=104.0,
            close=105.2,
            high=105.3,
            low=104.0,
        )
    )

    assert signal.action == 'BUY'
    assert signal.reason == 'intraday_bullish_breakout'
    assert signal.confidence == 0.8
    assert signal.metadata is not None
    assert signal.metadata['atr_percent'] > 0


def test_intraday_trend_emits_sell_when_session_and_breakdown_are_bearish():
    strategy = IntradayTrendStrategy(config())

    strategy.on_candle(candle(open=105.0, close=105.0, high=105.2, low=104.9))
    strategy.on_candle(candle(open=104.0, close=104.0, high=104.2, low=103.9))
    strategy.on_candle(candle(open=103.0, close=103.0, high=103.2, low=102.9))
    strategy.on_candle(candle(open=102.0, close=102.0, high=102.2, low=101.9))
    strategy.on_candle(candle(open=101.0, close=101.0, high=101.2, low=100.9))

    signal = strategy.on_candle(
        candle(
            open=101.0,
            close=99.8,
            high=101.0,
            low=99.7,
        )
    )

    assert signal.action == 'SELL'
    assert signal.reason == 'intraday_bearish_breakdown'
    assert signal.confidence == 0.8
    assert signal.metadata is not None
    assert signal.metadata['atr_percent'] > 0


def test_intraday_trend_returns_hold_when_session_move_is_neutral():
    strategy = IntradayTrendStrategy(config())

    strategy.on_candle(candle(open=100.0, close=100.0))
    strategy.on_candle(candle(open=100.0, close=100.01))
    strategy.on_candle(candle(open=100.01, close=100.02))
    strategy.on_candle(candle(open=100.02, close=100.03))
    strategy.on_candle(candle(open=100.03, close=100.04))

    signal = strategy.on_candle(candle(open=100.04, close=100.05))

    assert signal.action == 'HOLD'
    assert signal.reason == 'session_trend_neutral'


def test_intraday_trend_does_not_emit_short_when_short_is_disabled():
    strategy = IntradayTrendStrategy(config(allow_short=False))

    strategy.on_candle(candle(open=105.0, close=105.0, high=105.2, low=104.9))
    strategy.on_candle(candle(open=104.0, close=104.0, high=104.2, low=103.9))
    strategy.on_candle(candle(open=103.0, close=103.0, high=103.2, low=102.9))
    strategy.on_candle(candle(open=102.0, close=102.0, high=102.2, low=101.9))
    strategy.on_candle(candle(open=101.0, close=101.0, high=101.2, low=100.9))

    signal = strategy.on_candle(
        candle(
            open=101.0,
            close=99.8,
            high=101.0,
            low=99.7,
        )
    )

    assert signal.action == 'HOLD'
    assert signal.reason == 'short_signals_disabled_by_strategy'


def test_intraday_trend_rejects_invalid_fast_and_slow_lookbacks():
    with pytest.raises(ValueError, match='fast_lookback must be lower than slow_lookback'):
        IntradayTrendStrategy(
            IntradayTrendStrategyConfig(
                fast_lookback=5,
                slow_lookback=5,
            )
        )
