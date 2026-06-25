from datetime import datetime, timezone, timedelta

from app.market.models import Candle
from app.strategies.breakout import BreakoutStrategy


def candle(
    close: float,
    high: float | None = None,
    low: float | None = None,
    opened_at: datetime | None = None,
) -> Candle:
    opened_at = opened_at or datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    closed_at = opened_at + timedelta(minutes=1)

    high = high if high is not None else close
    low = low if low is not None else close

    return Candle(
        symbol='BTC',
        timeframe_seconds=60,
        open=close,
        high=high,
        low=low,
        close=close,
        volume=None,
        opened_at=opened_at,
        closed_at=closed_at,
    )


def test_breakout_strategy_returns_hold_while_warming_up():
    strategy = BreakoutStrategy(lookback=3, min_breakout_percent=0.01)

    signal = strategy.on_candle(candle(100))

    assert signal.action == 'HOLD'
    assert signal.reason == 'warming_up_candles'


def test_breakout_strategy_emits_buy_signal_after_candle_breakout():
    strategy = BreakoutStrategy(lookback=3, min_breakout_percent=0.01)

    strategy.on_candle(candle(close=100, high=100))
    strategy.on_candle(candle(close=101, high=101))
    strategy.on_candle(candle(close=102, high=102))

    signal = strategy.on_candle(candle(close=103, high=103))

    assert signal.action == 'BUY'
    assert signal.reason == 'candle_breakout_above_recent_range'


def test_breakout_strategy_returns_hold_when_inside_recent_range():
    strategy = BreakoutStrategy(lookback=3, min_breakout_percent=0.01)

    strategy.on_candle(candle(close=100, high=100))
    strategy.on_candle(candle(close=101, high=101))
    strategy.on_candle(candle(close=102, high=102))

    signal = strategy.on_candle(candle(close=101.5, high=102))

    assert signal.action == 'HOLD'
    assert signal.reason == 'candle_inside_recent_range'


def test_snapshot_strategy_is_disabled_for_now():
    from app.market.models import MarketSnapshot

    strategy = BreakoutStrategy(lookback=3, min_breakout_percent=0.01)

    signal = strategy.on_snapshot(
        MarketSnapshot.now('BTC', bid=100, ask=101, last=100.5)
    )

    assert signal.action == 'HOLD'
    assert signal.reason == 'snapshot_strategy_disabled'