from dataclasses import dataclass
from enum import StrEnum


class AssetClass(StrEnum):
    CRYPTO = 'CRYPTO'
    EQUITY_US = 'EQUITY_US'
    EQUITY_EU = 'EQUITY_EU'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True)
class InstrumentProfile:
    symbol: str
    asset_class: AssetClass


@dataclass(frozen=True)
class RiskProfile:
    asset_class: AssetClass
    max_position_size_percent: float
    stop_loss_percent: float
    take_profit_percent: float
    estimated_round_trip_fees: float
    min_expected_net_profit: float
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
    breakeven_stop_enabled: bool
    breakeven_trigger_percent: float
    breakeven_buffer_percent: float
    trailing_stop_enabled: bool
    trailing_stop_trigger_percent: float
    trailing_stop_distance_percent: float
