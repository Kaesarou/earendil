from dataclasses import dataclass

from app.strategies.models import AssetStrategyConfig, StrategyProfileConfig, TrendStrategyConfig


@dataclass(frozen=True)
class BalancedStrategyConfig(StrategyProfileConfig):
    name: str = 'balanced'
    candidate_selection_top_n: int = 2
    crypto: AssetStrategyConfig = AssetStrategyConfig(
        trend=TrendStrategyConfig(
            lookback=3,
            fast_lookback = 5,
            slow_lookback = 15,
            session_lookback=30,
            min_session_move_percent=0.30,
            min_breakout_percent=0.05,
            min_candle_range_percent=0.04,
            min_close_position_percent=75.0,
            atr_lookback=14,
            market_regime_filter_enabled=True,
            market_regime_min_trend_strength_percent=0.10,
            market_regime_min_atr_percent=0.02,
            market_regime_max_atr_percent=0.80,
            market_regime_max_noise_ratio=2.0,
            snapshot_momentum_window_seconds=180,
            min_snapshot_momentum_percent=0.25,
        )
    )
    equity_us: AssetStrategyConfig = AssetStrategyConfig(
        trend=TrendStrategyConfig(
            lookback=3,
            fast_lookback = 5,
            slow_lookback = 15,
            session_lookback=30,
            min_session_move_percent=0.20,
            min_breakout_percent=0.04,
            min_candle_range_percent=0.03,
            min_close_position_percent=72.0,
            atr_lookback=14,
            market_regime_filter_enabled=True,
            market_regime_min_trend_strength_percent=0.05,
            market_regime_min_atr_percent=0.01,
            market_regime_max_atr_percent=0.50,
            market_regime_max_noise_ratio=2.0,
            snapshot_momentum_window_seconds=180,
            min_snapshot_momentum_percent=0.20,
        )
    )
    equity_eu: AssetStrategyConfig = AssetStrategyConfig(
        trend=TrendStrategyConfig(
            lookback=3,
            fast_lookback = 5,
            slow_lookback = 15,
            session_lookback=30,
            min_session_move_percent=0.18,
            min_breakout_percent=0.04,
            min_candle_range_percent=0.03,
            min_close_position_percent=72.0,
            atr_lookback=14,
            market_regime_filter_enabled=True,
            market_regime_min_trend_strength_percent=0.05,
            market_regime_min_atr_percent=0.01,
            market_regime_max_atr_percent=0.50,
            market_regime_max_noise_ratio=2.0,
            snapshot_momentum_window_seconds=180,
            min_snapshot_momentum_percent=0.20,
        )
    )
