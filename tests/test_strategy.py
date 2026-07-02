from datetime import datetime, timedelta, timezone

import pytest

from app.instruments.models import AssetClass
from app.market.models import Candle, MarketSnapshot
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


def snapshot(
    last: float,
    bid: float | None = None,
    ask: float | None = None,
    timestamp: datetime | None = None,
) -> MarketSnapshot:
    timestamp = timestamp or datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    bid = bid if bid is not None else last * 0.999
    ask = ask if ask is not None else last * 1.001

    return MarketSnapshot(
        symbol='AAPL',
        bid=bid,
        ask=ask,
        last=last,
        timestamp=timestamp,
    )


def config(
    market_regime_filter_enabled: bool = False,
    market_regime_min_trend_strength_percent: float = 0.02,
    market_regime_min_atr_percent: float = 0.0,
    market_regime_max_atr_percent: float = 0.0,
    market_regime_max_noise_ratio: float = 0.0,
    snapshot_momentum_window_seconds: int = 180,
    min_snapshot_momentum_percent: float = 0.05,
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
        snapshot_momentum_window_seconds=snapshot_momentum_window_seconds,
        min_snapshot_momentum_percent=min_snapshot_momentum_percent,
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


def feed_bearish_breakdown_setup(strategy: TrendStrategy):
    strategy.on_candle(candle(open=105.0, close=105.0, high=105.2, low=104.9))
    strategy.on_candle(candle(open=104.0, close=104.0, high=104.2, low=103.9))
    strategy.on_candle(candle(open=103.0, close=103.0, high=103.2, low=102.9))
    strategy.on_candle(candle(open=102.0, close=102.0, high=102.2, low=101.9))
    strategy.on_candle(candle(open=101.0, close=101.0, high=101.2, low=100.9))

    return strategy.on_candle(
        candle(
            open=101.0,
            close=99.8,
            high=101.0,
            low=99.7,
        )
    )


def feed_bullish_flat_breakout_candle(strategy: TrendStrategy):
    strategy.on_candle(candle(open=100.0, close=100.0, high=100.1, low=99.8))
    strategy.on_candle(candle(open=101.0, close=101.0, high=101.1, low=100.8))
    strategy.on_candle(candle(open=102.0, close=102.0, high=102.1, low=101.8))
    strategy.on_candle(candle(open=103.0, close=103.0, high=103.1, low=102.8))
    strategy.on_candle(candle(open=104.0, close=104.0, high=104.1, low=103.8))

    return strategy.on_candle(
        candle(
            open=105.2,
            close=105.2,
            high=105.2,
            low=105.2,
        )
    )


def feed_bearish_flat_breakdown_candle(strategy: TrendStrategy):
    strategy.on_candle(candle(open=105.0, close=105.0, high=105.2, low=104.9))
    strategy.on_candle(candle(open=104.0, close=104.0, high=104.2, low=103.9))
    strategy.on_candle(candle(open=103.0, close=103.0, high=103.2, low=102.9))
    strategy.on_candle(candle(open=102.0, close=102.0, high=102.2, low=101.9))
    strategy.on_candle(candle(open=101.0, close=101.0, high=101.2, low=100.9))

    return strategy.on_candle(
        candle(
            open=99.8,
            close=99.8,
            high=99.8,
            low=99.8,
        )
    )


def feed_snapshots(strategy: TrendStrategy, prices: list[float]):
    for index, price in enumerate(prices):
        strategy.on_snapshot(
            snapshot(
                last=price,
                timestamp=datetime(2026, 6, 25, 12, index, tzinfo=timezone.utc),
            )
        )


def test_trend_strategy_emits_buy_when_session_and_breakout_are_bullish():
    strategy = TrendStrategy(config())
    feed_snapshots(strategy, [104.8, 104.9, 105.0, 105.2])

    signal = feed_bullish_breakout_setup(strategy)

    assert signal.action == 'BUY'
    assert signal.reason == 'trend_bullish_breakout'
    assert signal.confidence == 0.8
    assert signal.metadata is not None
    assert signal.metadata['atr_percent'] > 0
    assert signal.metadata['market_regime'] == 'TRENDING'
    assert signal.metadata['candle_reliable'] is True
    assert signal.metadata['snapshot_momentum_confirmed'] is True
    assert signal.metadata['entry_confirmation_source'] == 'candle_and_snapshot_momentum'


def test_trend_strategy_emits_sell_when_session_and_breakdown_are_bearish():
    strategy = TrendStrategy(config())
    feed_snapshots(strategy, [100.2, 100.1, 100.0, 99.8])

    signal = feed_bearish_breakdown_setup(strategy)

    assert signal.action == 'SELL'
    assert signal.reason == 'trend_bearish_breakdown'
    assert signal.confidence == 0.8
    assert signal.metadata is not None
    assert signal.metadata['atr_percent'] > 0
    assert signal.metadata['market_regime'] == 'TRENDING'
    assert signal.metadata['candle_reliable'] is True
    assert signal.metadata['snapshot_momentum_confirmed'] is True
    assert signal.metadata['entry_confirmation_source'] == 'candle_and_snapshot_momentum'


def test_reliable_bullish_breakout_is_rejected_when_snapshot_momentum_is_too_weak():
    strategy = TrendStrategy(
        config(
            snapshot_momentum_window_seconds=180,
            min_snapshot_momentum_percent=0.20,
        )
    )
    feed_snapshots(strategy, [105.0, 105.02, 105.04, 105.05])

    signal = feed_bullish_breakout_setup(strategy)

    assert signal.action == 'HOLD'
    assert signal.reason == 'snapshot_bullish_momentum_not_confirmed'
    assert signal.metadata is not None
    assert signal.metadata['candle_reliable'] is True
    assert signal.metadata['snapshot_momentum_confirmed'] is False
    assert signal.metadata['entry_confirmation_source'] == 'candle_and_snapshot_momentum'


def test_reliable_bullish_breakout_is_rejected_when_snapshot_momentum_is_negative():
    strategy = TrendStrategy(
        config(
            snapshot_momentum_window_seconds=180,
            min_snapshot_momentum_percent=0.20,
        )
    )
    feed_snapshots(strategy, [105.2, 105.1, 105.0, 104.9])

    signal = feed_bullish_breakout_setup(strategy)

    assert signal.action == 'HOLD'
    assert signal.reason == 'snapshot_bullish_momentum_not_confirmed'
    assert signal.metadata is not None
    assert signal.metadata['snapshot_momentum_percent'] < 0


def test_reliable_bearish_breakdown_is_rejected_when_snapshot_momentum_is_too_weak():
    strategy = TrendStrategy(
        config(
            snapshot_momentum_window_seconds=180,
            min_snapshot_momentum_percent=0.20,
        )
    )
    feed_snapshots(strategy, [99.8, 99.78, 99.76, 99.75])

    signal = feed_bearish_breakdown_setup(strategy)

    assert signal.action == 'HOLD'
    assert signal.reason == 'snapshot_bearish_momentum_not_confirmed'
    assert signal.metadata is not None
    assert signal.metadata['candle_reliable'] is True
    assert signal.metadata['snapshot_momentum_confirmed'] is False
    assert signal.metadata['entry_confirmation_source'] == 'candle_and_snapshot_momentum'


def test_reliable_bearish_breakdown_is_rejected_when_snapshot_momentum_is_positive():
    strategy = TrendStrategy(
        config(
            snapshot_momentum_window_seconds=180,
            min_snapshot_momentum_percent=0.20,
        )
    )
    feed_snapshots(strategy, [99.8, 99.9, 100.0, 100.1])

    signal = feed_bearish_breakdown_setup(strategy)

    assert signal.action == 'HOLD'
    assert signal.reason == 'snapshot_bearish_momentum_not_confirmed'
    assert signal.metadata is not None
    assert signal.metadata['snapshot_momentum_percent'] > 0


def test_reliable_breakout_is_rejected_when_snapshot_window_is_not_available():
    strategy = TrendStrategy(
        config(
            snapshot_momentum_window_seconds=180,
            min_snapshot_momentum_percent=0.20,
        )
    )

    signal = feed_bullish_breakout_setup(strategy)

    assert signal.action == 'HOLD'
    assert signal.reason == 'snapshot_bullish_momentum_not_confirmed'
    assert signal.metadata is not None
    assert signal.metadata['snapshot_momentum_confirmed'] is False
    assert signal.metadata['snapshot_momentum_rejection_detail'] == (
        'snapshot_momentum_not_enough_time_window'
    )


def test_snapshot_momentum_confirmation_uses_time_window_not_snapshot_count():
    strategy = TrendStrategy(
        config(
            snapshot_momentum_window_seconds=180,
            min_snapshot_momentum_percent=0.20,
        )
    )

    base_time = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    strategy.on_snapshot(snapshot(last=100.0, timestamp=base_time))
    strategy.on_snapshot(snapshot(last=110.0, timestamp=base_time + timedelta(seconds=120)))
    strategy.on_snapshot(snapshot(last=100.3, timestamp=base_time + timedelta(seconds=180)))

    confirmed, reason, metadata = strategy._snapshot_momentum_confirmation(
        side='long',
        mode='entry_confirmation',
    )

    assert confirmed is True
    assert reason == 'snapshot_momentum_confirmed'
    assert metadata['snapshot_reference_price'] == 100.0
    assert metadata['snapshot_current_price'] == 100.3
    assert metadata['snapshot_momentum_percent'] == pytest.approx(0.3)


def test_trend_strategy_uses_snapshot_momentum_fallback_for_flat_bullish_candle():
    strategy = TrendStrategy(config())
    feed_snapshots(strategy, [102.0, 103.0, 104.0, 105.3])

    signal = feed_bullish_flat_breakout_candle(strategy)

    assert signal.action == 'BUY'
    assert signal.reason == 'trend_bullish_snapshot_momentum'
    assert signal.confidence == 0.75
    assert signal.metadata is not None
    assert signal.metadata['candle_reliable'] is False
    assert signal.metadata['candle_unreliable_reason'] == 'flat_candle_ohlc'
    assert signal.metadata['snapshot_momentum_confirmed'] is True
    assert signal.metadata['snapshot_momentum_side'] == 'long'
    assert signal.metadata['confirmation_source'] == 'snapshot_momentum'
    assert signal.metadata['breakout_percent'] == signal.metadata['snapshot_breakout_percent']


def test_trend_strategy_rejects_flat_bullish_candle_when_snapshot_momentum_is_weak():
    strategy = TrendStrategy(config())
    feed_snapshots(strategy, [105.2, 105.19, 105.18, 105.17])

    signal = feed_bullish_flat_breakout_candle(strategy)

    assert signal.action == 'HOLD'
    assert signal.reason == 'snapshot_bullish_momentum_not_confirmed'
    assert signal.metadata is not None
    assert signal.metadata['candle_reliable'] is False
    assert signal.metadata['snapshot_momentum_confirmed'] is False


def test_trend_strategy_uses_snapshot_momentum_fallback_for_flat_bearish_candle():
    strategy = TrendStrategy(config())
    feed_snapshots(strategy, [103.0, 102.0, 101.0, 99.7])

    signal = feed_bearish_flat_breakdown_candle(strategy)

    assert signal.action == 'SELL'
    assert signal.reason == 'trend_bearish_snapshot_momentum'
    assert signal.confidence == 0.75
    assert signal.metadata is not None
    assert signal.metadata['candle_reliable'] is False
    assert signal.metadata['candle_unreliable_reason'] == 'flat_candle_ohlc'
    assert signal.metadata['snapshot_momentum_confirmed'] is True
    assert signal.metadata['snapshot_momentum_side'] == 'short'
    assert signal.metadata['confirmation_source'] == 'snapshot_momentum'
    assert signal.metadata['breakdown_percent'] == signal.metadata['snapshot_breakdown_percent']


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

    crypto_trend = profile.trend_config_for_asset_class(AssetClass.CRYPTO)
    equity_us_trend = profile.trend_config_for_asset_class(AssetClass.EQUITY_US)
    equity_eu_trend = profile.trend_config_for_asset_class(AssetClass.EQUITY_EU)

    assert crypto_trend.min_session_move_percent == 0.30
    assert crypto_trend.snapshot_momentum_window_seconds == 180
    assert crypto_trend.min_snapshot_momentum_percent == 0.25
    assert equity_us_trend.snapshot_momentum_window_seconds == 180
    assert equity_us_trend.min_snapshot_momentum_percent == 0.20
    assert equity_eu_trend.snapshot_momentum_window_seconds == 180
    assert equity_eu_trend.min_snapshot_momentum_percent == 0.20
    assert profile.pre_scan_config_for_asset_class(AssetClass.CRYPTO).min_score == 120.0


def test_strategy_profile_from_name_resolves_aggressive_profile():
    profile = strategy_profile_from_name('aggressive')

    assert isinstance(profile, AggressiveStrategyConfig)
    assert profile.name == 'aggressive'

    crypto_trend = profile.trend_config_for_asset_class(AssetClass.CRYPTO)
    equity_us_trend = profile.trend_config_for_asset_class(AssetClass.EQUITY_US)
    equity_eu_trend = profile.trend_config_for_asset_class(AssetClass.EQUITY_EU)

    assert crypto_trend.min_session_move_percent == 0.20
    assert crypto_trend.snapshot_momentum_window_seconds == 180
    assert crypto_trend.min_snapshot_momentum_percent == 0.20
    assert equity_us_trend.snapshot_momentum_window_seconds == 180
    assert equity_us_trend.min_snapshot_momentum_percent == 0.15
    assert equity_eu_trend.snapshot_momentum_window_seconds == 180
    assert equity_eu_trend.min_snapshot_momentum_percent == 0.15
    assert profile.pre_scan_config_for_asset_class(AssetClass.CRYPTO).min_score == 105.0


def test_strategy_profile_from_name_rejects_unknown_profile():
    with pytest.raises(ValueError, match='Unsupported strategy aggressiveness'):
        strategy_profile_from_name('berserker')
