from dataclasses import dataclass

from app.instruments.base_configs import CRYPTO_CONFIG, EQUITY_EU_CONFIG, EQUITY_US_CONFIG
from app.instruments.models import TrendStrategyConfig
from app.strategies.models import StrategyProfileConfig


@dataclass(frozen=True)
class BalancedStrategyConfig(StrategyProfileConfig):
    name: str = 'balanced'
    candidate_selection_top_n: int = 2
    crypto: TrendStrategyConfig = CRYPTO_CONFIG.trend
    equity_us: TrendStrategyConfig = EQUITY_US_CONFIG.trend
    equity_eu: TrendStrategyConfig = EQUITY_EU_CONFIG.trend
