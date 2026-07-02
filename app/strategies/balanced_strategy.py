from dataclasses import dataclass

from app.execution.pre_scan import PreScanConfig
from app.strategies.models import AssetStrategyConfig, StrategyProfileConfig, TrendStrategyConfig


@dataclass(frozen=True)
class BalancedStrategyConfig(StrategyProfileConfig):
    name: str = 'balanced'
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
        ),
        pre_scan=PreScanConfig(
            enabled=True,
            top_n=2,
            min_score=120.0,
            allowed_market_regimes=('TRENDING',),
            min_session_move_percent=0.30,
            min_trend_strength_percent=0.10,
            min_atr_percent=0.02,
            max_atr_percent=0.80,
            max_noise_ratio=2.0,
        ),
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
        ),
        pre_scan=PreScanConfig(
            enabled=True,
            top_n=2,
            min_score=115.0,
            allowed_market_regimes=('TRENDING',),
            min_session_move_percent=0.20,
            min_trend_strength_percent=0.05,
            min_atr_percent=0.01,
            max_atr_percent=0.50,
            max_noise_ratio=2.0,
        ),
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
        ),
        pre_scan=PreScanConfig(
            enabled=True,
            top_n=2,
            min_score=115.0,
            allowed_market_regimes=('TRENDING',),
            min_session_move_percent=0.18,
            min_trend_strength_percent=0.05,
            min_atr_percent=0.01,
            max_atr_percent=0.50,
            max_noise_ratio=2.0,
        ),
    )