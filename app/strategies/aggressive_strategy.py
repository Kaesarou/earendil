from dataclasses import dataclass

from app.execution.pre_scan import PreScanConfig
from app.strategies.models import AssetStrategyConfig, StrategyProfileConfig, TrendStrategyConfig


@dataclass(frozen=True)
class AggressiveStrategyConfig(StrategyProfileConfig):
    name: str = 'aggressive'
    pre_scan_top_n: int = 2
    crypto: AssetStrategyConfig = AssetStrategyConfig(
        trend=TrendStrategyConfig(
            lookback=3,
            fast_lookback = 5,
            slow_lookback = 15,
            session_lookback=20,
            min_session_move_percent=0.20,
            min_breakout_percent=0.05,
            min_candle_range_percent=0.04,
            min_close_position_percent=70.0,
            atr_lookback=14,
            market_regime_filter_enabled=True,
            market_regime_min_trend_strength_percent=0.03,
            market_regime_min_atr_percent=0.02,
            market_regime_max_atr_percent=0.80,
            market_regime_max_noise_ratio=2.0,
            snapshot_momentum_window_seconds=180,
            min_snapshot_momentum_percent=0.20,
        )
    )
    equity_us: AssetStrategyConfig = AssetStrategyConfig(
        trend=TrendStrategyConfig(
            lookback=3,
            fast_lookback = 5,
            slow_lookback = 15,
            session_lookback=20,
            min_session_move_percent=0.12,
            min_breakout_percent=0.03,
            min_candle_range_percent=0.02,
            min_close_position_percent=68.0,
            atr_lookback=14,
            market_regime_filter_enabled=True,
            market_regime_min_trend_strength_percent=0.02,
            market_regime_min_atr_percent=0.005,
            market_regime_max_atr_percent=0.70,
            market_regime_max_noise_ratio=2.5,
            snapshot_momentum_window_seconds=180,
            min_snapshot_momentum_percent=0.15,
        )
    )
    equity_eu: AssetStrategyConfig = AssetStrategyConfig(
        trend=TrendStrategyConfig(
            lookback=3,
            fast_lookback = 5,
            slow_lookback = 15,
            session_lookback=20,
            min_session_move_percent=0.10,
            min_breakout_percent=0.03,
            min_candle_range_percent=0.02,
            min_close_position_percent=68.0,
            atr_lookback=14,
            market_regime_filter_enabled=True,
            market_regime_min_trend_strength_percent=0.02,
            market_regime_min_atr_percent=0.005,
            market_regime_max_atr_percent=0.70,
            market_regime_max_noise_ratio=2.5,
            snapshot_momentum_window_seconds=180,
            min_snapshot_momentum_percent=0.15,
        )
    )
