from dataclasses import dataclass

from app.instruments.models import AssetClass, InstrumentConfig, RiskProfile, TrendStrategyConfig
from app.risk.stale_position_guard import StalePositionConfig
from app.risk.trade_cost_model import TradeCostConfig


@dataclass(frozen=True)
class EquityEuConfig(InstrumentConfig):
    trend: TrendStrategyConfig = TrendStrategyConfig(
        lookback=3,
        fast_lookback=5,
        slow_lookback=15,
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
    risk: RiskProfile = RiskProfile(
        asset_class=AssetClass.EQUITY_EU,
        max_position_size_percent=0.75,
        stop_loss_percent=0.80,
        take_profit_percent=1.40,
        force_close_enabled=False,
        force_close_hour=17,
        force_close_minute=25,
        max_spread_percent=0.15,
        min_move_spread_ratio=3.0,
        dynamic_sl_tp_enabled=False,
        stop_loss_atr_multiplier=1.2,
        take_profit_atr_multiplier=2.0,
        min_stop_loss_percent=0.4,
        max_stop_loss_percent=1.5,
        min_take_profit_percent=0.8,
        max_take_profit_percent=3.0,
        breakeven_stop_enabled=True,
        breakeven_trigger_percent=1.0,
        breakeven_buffer_percent=0.0,
        trailing_stop_enabled=True,
        trailing_stop_trigger_percent=1.5,
        trailing_stop_distance_percent=0.8,
        stale_position=StalePositionConfig(
            enabled=True,
            max_age_minutes=75,
            min_favorable_move_percent=0.35,
            buffer_percent=0.10,
        ),
        trade_cost=TradeCostConfig(
            open_fee_percent=0.15,
            close_fee_percent=0.15,
            fixed_open_fee=0.0,
            fixed_close_fee=0.0,
            include_spread_cost=True,
            min_expected_net_profit_percent=0.10,
        ),
    )