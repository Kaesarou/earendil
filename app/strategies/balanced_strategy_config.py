from dataclasses import dataclass

from app.instruments.crypto_config import CryptoConfig
from app.instruments.equity_eu_config import EquityEuConfig
from app.instruments.equity_us_config import EquityUsConfig
from app.instruments.models import TrendStrategyConfig
from app.strategies.models import StrategyProfileConfig


@dataclass(frozen=True)
class BalancedStrategyConfig(StrategyProfileConfig):
    name: str = 'balanced'
    candidate_selection_top_n: int = 2
    crypto: TrendStrategyConfig =CryptoConfig().trend
    equity_us: TrendStrategyConfig =EquityUsConfig().trend
    equity_eu: TrendStrategyConfig =EquityEuConfig().trend
    
