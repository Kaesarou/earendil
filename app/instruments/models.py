from dataclasses import dataclass, field
from enum import StrEnum

from app.market.data_quality import MarketDataQualityConfig
from app.risk.stale_position_guard import StalePositionConfig
from app.risk.trade_cooldown import TradeCooldownConfig
from app.risk.trade_cost_model import TradeCostConfig
from app.strategies.entry_confirmation import EntryConfirmationConfig


class AssetClass(StrEnum):
    CRYPTO = 'CRYPTO'
    EQUITY_US = 'EQUITY_US'
    EQUITY_EU = 'EQUITY_EU'


@dataclass(frozen=True)
class InstrumentProfile:
    symbol: str
    asset_class: AssetClass


@dataclass(frozen=True)
class TpFeasibilityConfig:
    enabled: bool = True
    missing_data_penalty_points: float = 8.0
    feasibility_buffer_percent: float = 0.10
    tp_atr_soft_ratio: float = 2.0
    tp_atr_hard_ratio: float = 4.0
    tp_atr_severe_ratio: float = 6.0
    tp_momentum_soft_ratio: float = 4.0
    tp_momentum_hard_ratio: float = 12.0
    min_directional_momentum_percent: float = 0.03
    cost_to_tp_soft_ratio: float = 0.25
    cost_to_tp_hard_ratio: float = 0.45
    cost_to_tp_severe_ratio: float = 0.65
    cost_to_tp_hard_reject_ratio: float = 1.0
    late_move_soft_percent: float = 0.80
    late_move_hard_percent: float = 2.00
    near_extreme_distance_percent: float = 0.15
    max_penalty_points: float = 45.0
    moderate_score_cap: float = 110.0
    severe_score_cap: float = 95.0
    wait_confirmation_min_runway_score: float = 25.0
    wait_confirmation_severe_penalty: float = 40.0


@dataclass(frozen=True)
class MarketContextConfig:
    minimum_breadth_sample_size: int = 2
    minimum_sector_sample_size: int = 2
    minimum_breadth_coverage_ratio: float = 0.60
    bullish_advancing_ratio: float = 0.60
    bearish_advancing_ratio: float = 0.40
    minimum_benchmark_move_percent: float = 0.05
    unchanged_band_percent: float = 0.01
    maximum_context_age_seconds: int = 120
    momentum_window_seconds: int = 180
    require_benchmark: bool = False


@dataclass(frozen=True)
class EntryDecisionConfig:
    moderate_extension_percent: float = 0.12
    severe_extension_percent: float = 0.45
    wait_for_retest_penalty: float = 25.0
    severe_feasibility_penalty: float = 40.0
    minimum_retest_runway_score: float = 25.0
    context_opposition_is_hard_reject: bool = True
    require_context: bool = False


@dataclass(frozen=True)
class RiskProfile:
    asset_class: AssetClass
    max_position_size_percent: float
    stop_loss_percent: float
    take_profit_percent: float
    force_close_enabled: bool
    force_close_hour: int
    force_close_minute: int
    max_spread_percent: float
    min_move_spread_ratio: float
    dynamic_sl_tp_enabled: bool
    stop_loss_atr_multiplier: float
    take_profit_atr_multiplier: float
    min_stop_loss_percent: float
    max_stop_loss_percent: float
    min_take_profit_percent: float
    max_take_profit_percent: float
    breakeven_stop_enabled: bool = False
    breakeven_trigger_percent: float = 0.0
    breakeven_buffer_percent: float = 0.0
    trailing_stop_enabled: bool = False
    trailing_stop_trigger_percent: float = 0.0
    trailing_stop_distance_percent: float = 0.0
    trailing_stop_net_buffer_percent: float = 0.0
    stale_position: StalePositionConfig = field(default_factory=StalePositionConfig)
    trade_cooldown: TradeCooldownConfig = field(default_factory=TradeCooldownConfig)
    trade_cost: TradeCostConfig = field(default_factory=TradeCostConfig)
    tp_feasibility: TpFeasibilityConfig = field(default_factory=TpFeasibilityConfig)
    entry_confirmation: EntryConfirmationConfig = field(default_factory=EntryConfirmationConfig)


@dataclass(frozen=True)
class TrendStrategyConfig:
    lookback: int
    fast_lookback: int
    slow_lookback: int
    session_lookback: int
    min_session_move_percent: float
    min_breakout_percent: float
    min_candle_range_percent: float
    min_close_position_percent: float
    atr_lookback: int
    market_regime_filter_enabled: bool
    market_regime_min_trend_strength_percent: float
    market_regime_min_atr_percent: float
    market_regime_max_atr_percent: float
    market_regime_max_noise_ratio: float
    snapshot_momentum_window_seconds: int = 180
    min_snapshot_momentum_percent: float = 0.20


@dataclass(frozen=True)
class InstrumentConfig:
    trend: TrendStrategyConfig
    risk: RiskProfile
    market_data_quality: MarketDataQualityConfig = field(default_factory=MarketDataQualityConfig)
    market_context: MarketContextConfig = field(default_factory=MarketContextConfig)
    entry_decision: EntryDecisionConfig = field(default_factory=EntryDecisionConfig)
