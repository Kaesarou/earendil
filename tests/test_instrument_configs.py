from app.instruments.base_configs import CRYPTO_CONFIG, EQUITY_US_CONFIG
from app.instruments.config_overrides import with_trend_overrides
from app.instruments.models import AssetClass
from app.risk.profiles import risk_profiles_for_aggressiveness
from app.strategies.aggressive_strategy_config import AggressiveStrategyConfig
from app.strategies.balanced_strategy_config import BalancedStrategyConfig


def test_balanced_strategy_uses_base_instrument_trend_configs():
    profile = BalancedStrategyConfig()

    assert profile.crypto == CRYPTO_CONFIG.trend
    assert profile.equity_us == EQUITY_US_CONFIG.trend


def test_aggressive_strategy_overrides_only_declared_trend_fields():
    profile = AggressiveStrategyConfig()

    assert profile.crypto.session_lookback == 20
    assert profile.crypto.min_session_move_percent == 0.20
    assert profile.crypto.lookback == CRYPTO_CONFIG.trend.lookback
    assert profile.crypto.fast_lookback == CRYPTO_CONFIG.trend.fast_lookback
    assert profile.crypto.slow_lookback == CRYPTO_CONFIG.trend.slow_lookback
    assert profile.crypto.atr_lookback == CRYPTO_CONFIG.trend.atr_lookback


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


def test_risk_profiles_are_built_from_base_instrument_configs_with_profile_cooldown():
    balanced_profiles = risk_profiles_for_aggressiveness('balanced')
    aggressive_profiles = risk_profiles_for_aggressiveness('aggressive')

    assert balanced_profiles[AssetClass.CRYPTO].trade_cost == CRYPTO_CONFIG.risk.trade_cost
    assert aggressive_profiles[AssetClass.CRYPTO].trade_cost == CRYPTO_CONFIG.risk.trade_cost
    assert balanced_profiles[AssetClass.CRYPTO].trade_cooldown.after_take_profit_minutes == 30
    assert aggressive_profiles[AssetClass.CRYPTO].trade_cooldown.after_take_profit_minutes == 15
