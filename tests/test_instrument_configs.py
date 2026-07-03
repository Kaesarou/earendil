from app.instruments.base_configs import CRYPTO_CONFIG, EQUITY_US_CONFIG
from app.instruments.config_overrides import with_trend_overrides
from app.instruments.models import AssetClass
from app.risk.profiles import risk_profiles_for_aggressiveness
from app.strategies.aggressive_strategy_config import AggressiveStrategyConfig
from app.strategies.balanced_strategy_config import BalancedStrategyConfig


def test_balanced_strategy_uses_base_instrument_configs_with_profile_cooldown():
    profile = BalancedStrategyConfig()

    assert profile.crypto.trend == CRYPTO_CONFIG.trend
    assert profile.equity_us.trend == EQUITY_US_CONFIG.trend
    assert profile.crypto.risk.trade_cost == CRYPTO_CONFIG.risk.trade_cost
    assert profile.crypto.risk.trade_cooldown.after_take_profit_minutes == 30


def test_aggressive_strategy_overrides_only_declared_trend_fields():
    profile = AggressiveStrategyConfig()

    assert profile.crypto.trend.session_lookback == 20
    assert profile.crypto.trend.min_session_move_percent == 0.20
    assert profile.crypto.trend.lookback == CRYPTO_CONFIG.trend.lookback
    assert profile.crypto.trend.fast_lookback == CRYPTO_CONFIG.trend.fast_lookback
    assert profile.crypto.trend.slow_lookback == CRYPTO_CONFIG.trend.slow_lookback
    assert profile.crypto.trend.atr_lookback == CRYPTO_CONFIG.trend.atr_lookback
    assert profile.crypto.risk.trade_cost == CRYPTO_CONFIG.risk.trade_cost
    assert profile.crypto.risk.trade_cooldown.after_take_profit_minutes == 15


def test_trend_override_helper_preserves_base_risk_config():
    overridden = with_trend_overrides(
        CRYPTO_CONFIG,
        session_lookback=20,
        min_session_move_percent=0.20,
    )

    assert overridden.trend.session_lookback == 20
    assert overridden.trend.min_session_move_percent == 0.20
    assert overridden.trend.lookback == CRYPTO_CONFIG.trend.lookback
    assert overridden.risk == CRYPTO_CONFIG.risk


def test_strategy_profile_exposes_instrument_configs_and_risk_profiles():
    profile = BalancedStrategyConfig()

    assert profile.instrument_config_for_asset_class(AssetClass.CRYPTO) == profile.crypto
    assert profile.trend_config_for_asset_class(AssetClass.CRYPTO) == profile.crypto.trend
    assert profile.risk_profile_for_asset_class(AssetClass.CRYPTO) == profile.crypto.risk
    assert profile.risk_profiles()[AssetClass.CRYPTO] == profile.crypto.risk


def test_risk_profiles_are_derived_from_strategy_profiles():
    balanced_profiles = risk_profiles_for_aggressiveness('balanced')
    aggressive_profiles = risk_profiles_for_aggressiveness('aggressive')

    assert balanced_profiles[AssetClass.CRYPTO] == BalancedStrategyConfig().crypto.risk
    assert aggressive_profiles[AssetClass.CRYPTO] == AggressiveStrategyConfig().crypto.risk
