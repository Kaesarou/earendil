from dataclasses import replace

from app.instruments.crypto_config import CryptoConfig
from app.instruments.equity_eu_config import EquityEuConfig
from app.instruments.equity_us_config import EquityUsConfig
from app.instruments.models import AssetClass, RiskProfile
from app.risk.trade_cooldown import TradeCooldownConfig
from app.risk.trade_cost_model import TradeCostConfig


BALANCED_TRADE_COOLDOWN = TradeCooldownConfig(
    after_take_profit_minutes=30,
    after_stop_loss_minutes=45,
    after_manual_close_minutes=15,
    after_unknown_close_minutes=15,
)

AGGRESSIVE_TRADE_COOLDOWN = TradeCooldownConfig(
    after_take_profit_minutes=15,
    after_stop_loss_minutes=30,
    after_manual_close_minutes=10,
    after_unknown_close_minutes=10,
)

def _risk_profiles_with_cooldown(
    trade_cooldown: TradeCooldownConfig,
) -> dict[AssetClass, RiskProfile]:
    return {
        AssetClass.CRYPTO: replace(
            CryptoConfig().risk,
            trade_cooldown=trade_cooldown,
        ),
        AssetClass.EQUITY_US: replace(
            EquityUsConfig().risk,
            trade_cooldown=trade_cooldown,
        ),
        AssetClass.EQUITY_EU: replace(
            EquityEuConfig().risk,
            trade_cooldown=trade_cooldown,
        ),
    }


BALANCED_RISK_PROFILES = _risk_profiles_with_cooldown(BALANCED_TRADE_COOLDOWN)
AGGRESSIVE_RISK_PROFILES = _risk_profiles_with_cooldown(AGGRESSIVE_TRADE_COOLDOWN)
DEFAULT_RISK_PROFILES: dict[AssetClass, RiskProfile] = BALANCED_RISK_PROFILES


def risk_profiles_for_aggressiveness(name: str) -> dict[AssetClass, RiskProfile]:
    normalized_name = name.strip().lower()

    if normalized_name in ('balanced', 'balance'):
        return BALANCED_RISK_PROFILES

    if normalized_name in ('aggressive', 'aggressif', 'aggressiv'):
        return AGGRESSIVE_RISK_PROFILES

    raise ValueError(
        f'Unsupported risk aggressiveness: {name}. '
        'Expected one of: balanced, aggressive.'
    )
