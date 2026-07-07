from dataclasses import dataclass

from app.instruments.models import AssetClass, InstrumentConfig, RiskProfile, TpFeasibilityConfig, TrendStrategyConfig
from app.risk.stale_position_guard import StalePositionConfig
from app.risk.trade_cost_model import TradeCostConfig


@dataclass(frozen=True)
class CryptoConfig(InstrumentConfig):
    trend: TrendStrategyConfig = TrendStrategyConfig(
        lookback=3,
        fast_lookback=5,
        slow_lookback=15,
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
    risk: RiskProfile = RiskProfile(
        asset_class=AssetClass.CRYPTO,
        max_position_size_percent=0.75,
        stop_loss_percent=1.50,
        take_profit_percent=3.00,
        force_close_enabled=False,
        force_close_hour=23,
        force_close_minute=59,
        max_spread_percent=0.35,
        min_move_spread_ratio=4.0,
        dynamic_sl_tp_enabled=False,
        stop_loss_atr_multiplier=1.5,
        take_profit_atr_multiplier=2.5,
        min_stop_loss_percent=0.8,
        max_stop_loss_percent=2.5,
        min_take_profit_percent=1.5,
        max_take_profit_percent=5.0,
        breakeven_stop_enabled=True,
        breakeven_trigger_percent=0.20,
        breakeven_buffer_percent=0.05,
        trailing_stop_enabled=True,
        trailing_stop_trigger_percent=2.20,
        trailing_stop_distance_percent=0.90,
        trailing_stop_net_buffer_percent=0.15,
        stale_position=StalePositionConfig(enabled=True, max_age_minutes=60, min_favorable_move_percent=0.80, buffer_percent=0.0),
        trade_cost=TradeCostConfig(open_fee_percent=1.00, close_fee_percent=1.00, fixed_open_fee=0.0, fixed_close_fee=0.0, include_spread_cost=True, min_expected_net_profit_percent=0.10),
        tp_feasibility=TpFeasibilityConfig(
            tp_atr_soft_ratio=1.8,
            tp_atr_hard_ratio=3.5,
            tp_atr_severe_ratio=5.0,
            tp_momentum_soft_ratio=3.0,
            tp_momentum_hard_ratio=10.0,
            min_directional_momentum_percent=0.05,
            cost_to_tp_soft_ratio=0.35,
            cost_to_tp_hard_ratio=0.55,
            cost_to_tp_severe_ratio=0.75,
            feasibility_buffer_percent=0.15,
        ),
    )
