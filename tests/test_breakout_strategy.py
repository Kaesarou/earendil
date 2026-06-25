from datetime import datetime, timedelta, timezone

import pytest

from app.market.models import Candle
from app.strategies.breakout import BreakoutStrategy, BreakoutStrategyConfig


def candle(
    open: float = 100.0,
    close: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    opened_at: datetime | None = None,
) -> Candle:
    opened_at = opened_at or datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    closed_at = opened_at + timedelta(minutes=1)

    high = high if high is not None else max(open, close)
    low = low if low is not None else min(open, close)

    return Candle(
        symbol='BTC',
        timeframe_seconds=60,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=None,
        opened_at=opened_at,
        closed_at=closed_at,
    )


def default_config() -> BreakoutStrategyConfig:
    return BreakoutStrategyConfig(
        lookback=3,
        min_breakout_percent=0.01,
        require_green_candle=True,
        min_close_position_percent=70.0,
        min_candle_range_percent=0.05,
    )


def warm_up(strategy: BreakoutStrategy) -> None:
    strategy.on_candle(candle(open=99.5, close=100.0, high=100.0, low=99.5))
    strategy.on_candle(candle(open=100.5, close=101.0, high=101.0, low=100.5))
    strategy.on_candle(candle(open=101.5, close=102.0, high=102.0, low=101.5))


def test_breakout_strategy_returns_hold_while_warming_up():
    strategy = BreakoutStrategy(default_config())

    signal = strategy.on_candle(candle(open=99.5, close=100.0))

    assert signal.action == 'HOLD'
    assert signal.reason == 'warming_up_candles'


def test_breakout_strategy_emits_buy_signal_after_confirmed_candle_breakout():
    strategy = BreakoutStrategy(default_config())
    warm_up(strategy)

    signal = strategy.on_candle(
        candle(
            open=102.0,
            close=103.0,
            high=103.1,
            low=102.0,
        )
    )

    assert signal.action == 'BUY'
    assert signal.reason == 'confirmed_candle_breakout_above_recent_range'
    assert signal.confidence == 0.7


def test_breakout_strategy_returns_hold_when_inside_recent_range():
    strategy = BreakoutStrategy(default_config())
    warm_up(strategy)

    signal = strategy.on_candle(candle(open=101.0, close=101.5, high=102.0, low=101.0))

    assert signal.action == 'HOLD'
    assert signal.reason == 'candle_inside_recent_range'


def test_breakout_strategy_rejects_breakout_when_candle_is_not_green():
    strategy = BreakoutStrategy(default_config())
    warm_up(strategy)

    signal = strategy.on_candle(
        candle(
            open=103.5,
            close=103.0,
            high=103.8,
            low=102.5,
        )
    )

    assert signal.action == 'HOLD'
    assert signal.reason == 'breakout_candle_not_green'


def test_breakout_strategy_rejects_breakout_when_candle_range_is_too_small():
    strategy = BreakoutStrategy(default_config())
    warm_up(strategy)

    signal = strategy.on_candle(
        candle(
            open=102.99,
            close=103.0,
            high=103.0,
            low=102.99,
        )
    )

    assert signal.action == 'HOLD'
    assert signal.reason == 'breakout_candle_range_too_small'


def test_breakout_strategy_rejects_breakout_when_close_is_not_near_high():
    strategy = BreakoutStrategy(default_config())
    warm_up(strategy)

    signal = strategy.on_candle(
        candle(
            open=102.0,
            close=103.0,
            high=104.0,
            low=102.0,
        )
    )

    assert signal.action == 'HOLD'
    assert signal.reason == 'breakout_close_not_near_high'


def test_breakout_strategy_can_disable_green_candle_requirement():
    strategy = BreakoutStrategy(
        BreakoutStrategyConfig(
            lookback=3,
            min_breakout_percent=0.01,
            require_green_candle=False,
            min_close_position_percent=50.0,
            min_candle_range_percent=0.05,
        )
    )
    warm_up(strategy)

    signal = strategy.on_candle(
        candle(
            open=103.5,
            close=103.4,
            high=103.8,
            low=102.5,
        )
    )

    assert signal.action == 'BUY'
    assert signal.reason == 'confirmed_candle_breakout_above_recent_range'


def test_breakout_strategy_rejects_invalid_close_position_percent():
    with pytest.raises(ValueError, match='min_close_position_percent must be between 0 and 100'):
        BreakoutStrategy(
            BreakoutStrategyConfig(
                min_close_position_percent=120.0,
            )
        )


def test_breakout_strategy_rejects_invalid_min_candle_range_percent():
    with pytest.raises(
        ValueError,
        match='min_candle_range_percent must be greater than or equal to 0',
    ):
        BreakoutStrategy(
            BreakoutStrategyConfig(
                min_candle_range_percent=-0.1,
            )
        )