from app.instruments.base_configs import CRYPTO_CONFIG, EQUITY_US_CONFIG
from app.instruments.models import AssetClass
from app.strategies.balanced_strategy_config import BalancedStrategyConfig


def test_balanced_strategy_uses_base_instrument_configs_with_profile_cooldown():
    profile = BalancedStrategyConfig()

    assert profile.crypto.trend == CRYPTO_CONFIG.trend
    assert profile.equity_us.trend == EQUITY_US_CONFIG.trend
    assert profile.crypto.risk.trade_cost == CRYPTO_CONFIG.risk.trade_cost
    assert profile.crypto.risk.trade_cooldown.after_take_profit_minutes == 30


def test_strategy_profile_exposes_instrument_configs():
    profile = BalancedStrategyConfig()

    assert profile.instrument_config_for_asset_class(AssetClass.CRYPTO) == profile.crypto
    assert profile.instrument_configs[AssetClass.EQUITY_US] == profile.equity_us
    assert profile.instrument_configs[AssetClass.EQUITY_EU] == profile.equity_eu
