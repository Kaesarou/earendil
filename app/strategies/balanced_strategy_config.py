from dataclasses import dataclass

from app.instruments.base_configs import CRYPTO_CONFIG, EQUITY_EU_CONFIG, EQUITY_US_CONFIG
from app.instruments.config_overrides import with_risk_overrides
from app.instruments.models import InstrumentConfig
from app.risk.trade_cooldown import TradeCooldownConfig
from app.strategies.models import StrategyProfileConfig

BALANCED_TRADE_COOLDOWN = TradeCooldownConfig(
    after_take_profit_minutes=30,
    after_stop_loss_minutes=45,
    after_manual_close_minutes=15,
    after_unknown_close_minutes=15,
)

BALANCED_CRYPTO_CONFIG = with_risk_overrides(
    CRYPTO_CONFIG,
    trade_cooldown=BALANCED_TRADE_COOLDOWN,
)
BALANCED_EQUITY_US_CONFIG = with_risk_overrides(
    EQUITY_US_CONFIG,
    trade_cooldown=BALANCED_TRADE_COOLDOWN,
)
BALANCED_EQUITY_EU_CONFIG = with_risk_overrides(
    EQUITY_EU_CONFIG,
    trade_cooldown=BALANCED_TRADE_COOLDOWN,
)


@dataclass(frozen=True)
class BalancedStrategyConfig(StrategyProfileConfig):
    name: str = 'balanced'
    candidate_selection_top_n: int = 2
    crypto: InstrumentConfig = BALANCED_CRYPTO_CONFIG
    equity_us: InstrumentConfig = BALANCED_EQUITY_US_CONFIG
    equity_eu: InstrumentConfig = BALANCED_EQUITY_EU_CONFIG
