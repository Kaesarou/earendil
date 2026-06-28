from datetime import datetime, timedelta, timezone

import pytest

from app.instruments.models import AssetClass
from app.market.models import Candle
from app.strategies.strategy import (
    AggressiveStrategyConfig,
    BalancedStrategyConfig,
    TrendStrategy,
    TrendStrategyConfig,
    strategy_profile_from_name,
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


def config(
    market_regime_filter_enabled: bool = False,
    market_regime_min_trend_strength_percent: float = 0.02,
    market_regime_min_atr_percent: float = 0.0,
    market_regime_max_atr_percent: float = 0.0,
    market_regime_max_noise_ratio: float = 0.0,
) -> TrendStrategyConfig:
    return TrendStrategyConfig(
        lookback=3,
        fast_lookback=3,
        slow_lookback=5,
        session_lookback=5,
        min_session_move_percent=0.1,
        min_breakout_percent=0.01,
        min_candle_range_percent=0.01,
        min_close_position_percent=70.0,
        atr_lookback=5,
        market_regime_filter_enabled=market_regime_filter_enabled,
        market_regime_min_trend_strength_percent=market_regime_min_trend_strength_percent,
        market_regime_min_atr_percent=market_regime_min_atr_percent,
        market_regime_max_atr_percent=market_regime_max_atr_percent,
        market_regime_max_noise_ratio=market_regime_max_noise_ratio,
    )


def feed_bullish_breakout_setup(strategy: TrendStrategy):
    strategy.on_candle(candle(open=100.0, close=100.0, high=100.1, low=99.8))
    strategy.on_candle(candle(open=101.0, close=101.0, high=101.1, low=100.8))
    strategy.on_candle(candle(open=102.0, close=102.0, high=102.1, low=101.8))
    strategy.on_candle(candle(open=103.0, close=103.0, high=103.1, low=102.8))
    strategy.on_candle(candle(open=104.0, close=104.0, high=104.1, low=103.8))

    return strategy.on_candle(
        candle(
            open=104.0,
            close=105.2,
            high=105.3,
            low=104.0,
        )
    )


def test_trend_strategy_emits_buy_when_session_and_breakout_are_bullish():
    strategy = TrendStrategy(config())

    signal = feed_bullish_breakout_setup(strategy)

    assert signal.action == 'BUY'
    assert signal.reason == 'trend_bullish_breakout'
    assert signal.confidence == 0.8
    assert signal.metadata is not None
    assert signal.metadata['atr_percent'] > 0
    assert signal.metadata['market_regime'] == 'TRENDING'


def test_trend_strategy_emits_sell_when_session_and_breakdown_are_bearish():
    strategy = TrendStrategy(config())

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
    assert signal.reason == 'trend_bearish_breakdown'
    assert signal.confidence == 0.8
    assert signal.metadata is not None
    assert signal.metadata['atr_percent'] > 0
    assert signal.metadata['market_regime'] == 'TRENDING'


def test_trend_strategy_returns_hold_when_session_move_is_neutral():
    strategy = TrendStrategy(config())

    strategy.on_candle(candle(open=100.0, close=100.0))
    strategy.on_candle(candle(open=100.0, close=100.01))
    strategy.on_candle(candle(open=100.01, close=100.02))
    strategy.on_candle(candle(open=100.02, close=100.03))
    strategy.on_candle(candle(open=100.03, close=100.04))

    signal = strategy.on_candle(candle(open=100.04, close=100.05))

    assert signal.action == 'HOLD'
    assert signal.reason == 'session_trend_neutral'


def test_trend_strategy_rejects_dead_market_when_regime_filter_is_enabled():
    strategy = TrendStrategy(config(market_regime_filter_enabled=True))

    strategy.on_candle(candle(open=100.0, close=100.0))
    strategy.on_candle(candle(open=100.0, close=100.01))
    strategy.on_candle(candle(open=100.01, close=100.02))
    strategy.on_candle(candle(open=100.02, close=100.03))
    strategy.on_candle(candle(open=100.03, close=100.04))

    signal = strategy.on_candle(candle(open=100.04, close=100.05))

    assert signal.action == 'HOLD'
    assert signal.reason == 'market_regime_dead_market'
    assert signal.metadata is not None
    assert signal.metadata['market_regime'] == 'DEAD_MARKET'


def test_trend_strategy_rejects_volatile_noisy_market_when_regime_filter_is_enabled():
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


def test_strategy_profile_from_name_resolves_balanced_profile():
    profile = strategy_profile_from_name('balanced')

    assert isinstance(profile, BalancedStrategyConfig)
    assert profile.name == 'balanced'
    assert profile.trend_config_for_asset_class(AssetClass.CRYPTO).min_session_move_percent == 0.30
    assert profile.pre_scan_config_for_asset_class(AssetClass.CRYPTO).min_score == 120.0


def test_strategy_profile_from_name_resolves_aggressive_profile():
    profile = strategy_profile_from_name('aggressive')

    assert isinstance(profile, AggressiveStrategyConfig)
    assert profile.name == 'aggressive'
    assert profile.trend_config_for_asset_class(AssetClass.CRYPTO).min_session_move_percent == 0.20
    assert profile.pre_scan_config_for_asset_class(AssetClass.CRYPTO).min_score == 105.0


def test_strategy_profile_from_name_rejects_unknown_profile():
    with pytest.raises(ValueError, match='Unsupported strategy aggressiveness'):
        strategy_profile_from_name('berserker')
