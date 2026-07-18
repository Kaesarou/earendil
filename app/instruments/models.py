from dataclasses import dataclass, field
from enum import StrEnum

from app.market.data_quality import MarketDataQualityConfig
from app.market.multi_timeframe import MultiTimeframeConfig
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
    feasibility_buffer_percent: float = 0.10
    missing_component_score: float = 45.0
    good_tp_to_atr_ratio: float = 1.50
    bad_tp_to_atr_ratio: float = 6.00
    good_tp_to_momentum_ratio: float = 3.00
    bad_tp_to_momentum_ratio: float = 12.00
    good_cost_to_tp_ratio: float = 0.10
    bad_cost_to_tp_ratio: float = 1.00
    good_movement_consumed_to_tp_ratio: float = 0.50
    bad_movement_consumed_to_tp_ratio: float = 2.00
    tp_vs_atr_weight: float = 0.35
    tp_vs_momentum_weight: float = 0.30
    cost_vs_tp_weight: float = 0.35
    entry_freshness_weight: float = 0.0
    maximum_score_contribution: float = 15.0
    cost_to_tp_hard_reject_ratio: float = 1.0

    def __post_init__(self) -> None:
        weights = (
            self.tp_vs_atr_weight
            + self.tp_vs_momentum_weight
            + self.cost_vs_tp_weight
            + self.entry_freshness_weight
        )
        if abs(weights - 1.0) > 1e-9:
            raise ValueError('TP feasibility component weights must sum to 1.0.')


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
    minimum_extension_to_tp_ratio: float = 0.20
    minimum_structural_retest_score: float = 25.0
    maximum_retest_candles: int = 5


@dataclass(frozen=True)
class DirectionalRiskOverride:
    stop_loss_percent: float
    take_profit_percent: float
    source: str
    stale_position: StalePositionConfig | None = None


@dataclass(frozen=True)
class RiskProfile:
    asset_class: AssetClass
    profile_key: str
    max_position_size_percent: float
    stop_loss_percent: float
    take_profit_percent: float
    force_close_enabled: bool
    force_close_hour: int
    force_close_minute: int
    max_spread_percent: float
    min_move_spread_ratio: float
    breakeven_stop_enabled: bool = False
    breakeven_trigger_percent: float = 0.0
    breakeven_buffer_percent: float = 0.0
    trailing_stop_enabled: bool = False
    trailing_stop_trigger_percent: float = 0.0
    trailing_stop_distance_percent: float = 0.0
    trailing_stop_net_buffer_percent: float = 0.0
    stale_position: StalePositionConfig = field(default_factory=StalePositionConfig)
    directional_overrides: dict[str, DirectionalRiskOverride] = field(
        default_factory=dict
    )
    trade_cooldown: TradeCooldownConfig = field(
        default_factory=TradeCooldownConfig
    )
    trade_cost: TradeCostConfig = field(default_factory=TradeCostConfig)
    tp_feasibility: TpFeasibilityConfig = field(
        default_factory=TpFeasibilityConfig
    )
    entry_confirmation: EntryConfirmationConfig = field(
        default_factory=EntryConfirmationConfig
    )

    def directional_override_for(
        self,
        side: str,
    ) -> DirectionalRiskOverride | None:
        return self.directional_overrides.get(side.strip().upper())

    def stale_position_for(self, side: str) -> StalePositionConfig:
        override = self.directional_override_for(side)
        if override is not None and override.stale_position is not None:
            return override.stale_position
        return self.stale_position


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
    market_data_quality: MarketDataQualityConfig = field(
        default_factory=MarketDataQualityConfig
    )
    market_context: MarketContextConfig = field(
        default_factory=MarketContextConfig
    )
    entry_decision: EntryDecisionConfig = field(
        default_factory=EntryDecisionConfig
    )
    multi_timeframe: MultiTimeframeConfig = field(
        default_factory=MultiTimeframeConfig
    )
