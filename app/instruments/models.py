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
