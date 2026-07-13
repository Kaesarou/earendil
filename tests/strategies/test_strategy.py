from datetime import datetime, timedelta, timezone

from app.instruments.models import TrendStrategyConfig
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal
from app.strategies.strategy import TrendStrategy


BASE_TIME = datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc)


def config(**overrides) -> TrendStrategyConfig:
    values = {
        'lookback': 3,
        'fast_lookback': 2,
        'slow_lookback': 3,
        'session_lookback': 3,
        'min_session_move_percent': 0.5,
        'min_breakout_percent': 0.1,
        'min_candle_range_percent': 0.05,
        'min_close_position_percent': 70.0,
        'atr_lookback': 3,
        'market_regime_filter_enabled': False,
        'market_regime_min_trend_strength_percent': 0.0,
        'market_regime_min_atr_percent': 0.0,
        'market_regime_max_atr_percent': 0.0,
        'market_regime_max_noise_ratio': 0.0,
    }
    values.update(overrides)
    return TrendStrategyConfig(**values)


def candle(
    close: float,
    open_price: float | None = None,
    high: float | None = None,
    low: float | None = None,
) -> Candle:
    actual_open = close if open_price is None else open_price
    return Candle(
        symbol='BTC',
        timeframe_seconds=60,
        open=actual_open,
        high=high if high is not None else max(actual_open, close),
        low=low if low is not None else min(actual_open, close),
        close=close,
        volume=None,
        opened_at=BASE_TIME,
        closed_at=BASE_TIME,
    )


def snapshot(last: float, seconds: int = 0) -> MarketSnapshot:
    return MarketSnapshot(
        symbol='BTC',
        bid=last,
        ask=last,
        last=last,
        timestamp=BASE_TIME + timedelta(seconds=seconds),
    )


def feed_prices(strategy: TrendStrategy, prices: list[float]) -> Signal | None:
    signal = None
    for price in prices:
        signal = strategy.on_candle(candle(price))
    return signal


def feed_bullish_breakout_setup(strategy: TrendStrategy, confirm_snapshots: bool = True):
    prices = [100, 100.2, 100.4, 100.6, 101.5]
    signal = None

    if confirm_snapshots:
        strategy.on_snapshot(snapshot(100.0, seconds=0))

    for price in prices[:-1]:
        signal = strategy.on_candle(candle(price))

    if confirm_snapshots:
        strategy.on_snapshot(snapshot(101.4, seconds=180))

    signal = strategy.on_candle(
        candle(
            close=prices[-1],
            open_price=100.7,
            high=101.55,
            low=100.65,
        )
    )
    return signal


def feed_bearish_breakdown_setup(strategy: TrendStrategy, confirm_snapshots: bool = True):
    prices = [101.5, 101.2, 101.0, 100.8, 100.0]
    signal = None

    if confirm_snapshots:
        strategy.on_snapshot(snapshot(101.5, seconds=0))

    for price in prices[:-1]:
        signal = strategy.on_candle(candle(price))

    if confirm_snapshots:
        strategy.on_snapshot(snapshot(100.1, seconds=180))

    signal = strategy.on_candle(
        candle(
            close=prices[-1],
            open_price=100.6,
            high=100.65,
            low=99.95,
        )
    )
    return signal


def test_strategy_holds_until_enough_candles_are_available():
    strategy = TrendStrategy(config(lookback=3))

    signal = strategy.on_candle(candle(100))

    assert signal.action == 'HOLD'
    assert signal.reason == 'warming_up_candles'


def test_strategy_emits_buy_on_bullish_breakout():
    strategy = TrendStrategy(config())

    signal = feed_bullish_breakout_setup(strategy)

    assert signal.action == 'BUY'
    assert signal.reason == 'trend_bullish_breakout'
    assert signal.setup_quality > 0
    assert signal.metadata is not None
    assert signal.metadata['session_move_percent'] > 0
    assert signal.metadata['breakout_percent'] > 0


def test_strategy_emits_sell_on_bearish_breakdown():
    strategy = TrendStrategy(config())

    signal = feed_bearish_breakdown_setup(strategy)

    assert signal.action == 'SELL'
    assert signal.reason == 'trend_bearish_breakdown'
    assert signal.setup_quality > 0
    assert signal.metadata is not None
    assert signal.metadata['session_move_percent'] < 0
    assert signal.metadata['breakdown_percent'] > 0


def test_strategy_holds_when_session_move_is_too_small():
    strategy = TrendStrategy(config(min_session_move_percent=1.0))

    signal: Signal = feed_prices(strategy, [100, 100.1, 100.2, 100.3, 100.4])

    assert signal.action == 'HOLD'
    assert signal.reason == 'session_trend_neutral'


def test_strategy_holds_when_bullish_close_is_not_near_high():
    strategy = TrendStrategy(config(min_close_position_percent=90.0))

    for price in [100, 100.2, 100.4, 100.6]:
        strategy.on_candle(candle(price))

    signal = strategy.on_candle(
        candle(
            close=101.5,
            open_price=100.7,
            high=102.0,
            low=100.65,
        )
    )

    assert signal.action == 'HOLD'
    assert signal.reason == 'long_close_not_near_high'


def test_strategy_holds_when_bearish_close_is_not_near_low():
    strategy = TrendStrategy(config(min_close_position_percent=90.0))

    for price in [101.5, 101.2, 101.0, 100.8]:
        strategy.on_candle(candle(price))

    signal = strategy.on_candle(
        candle(
            close=100.0,
            open_price=100.6,
            high=100.65,
            low=99.5,
        )
    )

    assert signal.action == 'HOLD'
    assert signal.reason == 'short_close_not_near_low'


def test_strategy_holds_when_candle_range_is_too_small():
    strategy = TrendStrategy(config(min_candle_range_percent=2.0))

    signal = feed_bullish_breakout_setup(strategy)

    assert signal.action == 'HOLD'
    assert signal.reason == 'candle_range_too_small'


def test_strategy_holds_when_bullish_breakout_is_too_small_without_snapshot_momentum():
    strategy = TrendStrategy(
        config(
            min_breakout_percent=1.0,
            min_snapshot_momentum_percent=1.0,
        )
    )

    signal = feed_bullish_breakout_setup(strategy, confirm_snapshots=False)

    assert signal.action == 'HOLD'
    assert signal.reason == 'bullish_breakout_not_confirmed'


def test_strategy_uses_snapshot_momentum_when_breakout_candle_is_unreliable():
    strategy = TrendStrategy(
        config(
            min_breakout_percent=1.0,
            min_snapshot_momentum_percent=0.2,
        )
    )

    strategy.on_snapshot(snapshot(100.0, seconds=0))
    for price in [100, 100.2, 100.4, 100.6]:
        strategy.on_candle(candle(price))

    strategy.on_snapshot(snapshot(101.4, seconds=180))
    signal = strategy.on_candle(
        candle(
            close=101.5,
            open_price=101.5,
            high=101.5,
            low=101.5,
        )
    )

    assert signal.action == 'BUY'
    assert signal.reason == 'trend_bullish_snapshot_momentum'
    assert signal.metadata is not None
    assert signal.metadata['snapshot_momentum_percent'] > 0


def test_strategy_holds_when_bearish_breakdown_is_too_small_without_snapshot_momentum():
    strategy = TrendStrategy(
        config(
            min_breakout_percent=1.0,
            min_snapshot_momentum_percent=1.0,
        )
    )

    signal = feed_bearish_breakdown_setup(strategy, confirm_snapshots=False)

    assert signal.action == 'HOLD'
    assert signal.reason == 'bearish_breakdown_not_confirmed'


def test_strategy_uses_snapshot_momentum_when_breakdown_candle_is_unreliable():
    strategy = TrendStrategy(
        config(
            min_breakout_percent=1.0,
            min_snapshot_momentum_percent=0.2,
        )
    )

    strategy.on_snapshot(snapshot(101.5, seconds=0))
    for price in [101.5, 101.2, 101.0, 100.8]:
        strategy.on_candle(candle(price))

    strategy.on_snapshot(snapshot(100.1, seconds=180))
    signal = strategy.on_candle(
        candle(
            close=100.0,
            open_price=100.0,
            high=100.0,
            low=100.0,
        )
    )

    assert signal.action == 'SELL'
    assert signal.reason == 'trend_bearish_snapshot_momentum'
    assert signal.metadata is not None
    assert signal.metadata['snapshot_momentum_percent'] < 0


def test_strategy_holds_when_market_regime_filter_detects_dead_market():
    strategy = TrendStrategy(
        config(
            market_regime_filter_enabled=True,
            market_regime_min_atr_percent=2.0,
        )
    )

    signal = feed_bullish_breakout_setup(strategy)

    assert signal.action == 'HOLD'
    assert signal.reason == 'market_regime_dead_market'
    assert signal.metadata is not None
    assert signal.metadata['market_regime'] == 'DEAD_MARKET'


def test_strategy_holds_when_market_regime_filter_detects_ranging():
    strategy = TrendStrategy(
        config(
            market_regime_filter_enabled=True,
            market_regime_min_trend_strength_percent=1.0,
            market_regime_min_atr_percent=0.0,
        )
    )

    signal = feed_bullish_breakout_setup(strategy)

    assert signal.action == 'HOLD'
    assert signal.reason == 'market_regime_ranging'
    assert signal.metadata is not None
    assert signal.metadata['market_regime'] == 'RANGING'


def test_strategy_holds_when_market_regime_filter_detects_overheated():
    strategy = TrendStrategy(
        config(
            market_regime_filter_enabled=True,
            market_regime_max_atr_percent=0.2,
        )
    )

    signal = feed_bullish_breakout_setup(strategy)

    assert signal.action == 'HOLD'
    assert signal.reason == 'market_regime_volatile_noisy'
    assert signal.metadata is not None
    assert signal.metadata['market_regime'] == 'VOLATILE_NOISY'


def test_strategy_holds_when_market_regime_filter_detects_noisy():
    strategy = TrendStrategy(
        config(
            market_regime_filter_enabled=True,
            market_regime_max_noise_ratio=0.2,
        )
    )

    signal = feed_bullish_breakout_setup(strategy)

    assert signal.action == 'HOLD'
    assert signal.reason == 'market_regime_volatile_noisy'
    assert signal.metadata is not None
    assert signal.metadata['market_regime'] == 'VOLATILE_NOISY'
