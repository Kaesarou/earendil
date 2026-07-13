from app.instruments.models import AssetClass
from app.strategies.balanced_strategy_config import BalancedStrategyConfig


def _risk_profiles():
    return BalancedStrategyConfig().risk_profiles()


def test_crypto_stale_position_config_is_enabled():
    config = _risk_profiles()[AssetClass.CRYPTO].stale_position

    assert config.enabled
    assert config.max_age_minutes == 60
    assert config.min_favorable_move_percent == 0.80
    assert config.buffer_percent == 0.0


def test_equity_us_stale_position_config_is_enabled():
    config = _risk_profiles()[AssetClass.EQUITY_US].stale_position

    assert config.enabled
    assert config.max_age_minutes == 60
    assert config.min_favorable_move_percent == 0.35
    assert config.buffer_percent == 0.10


def test_equity_eu_stale_position_config_is_enabled():
    config = _risk_profiles()[AssetClass.EQUITY_EU].stale_position

    assert config.enabled
    assert config.max_age_minutes == 75
    assert config.min_favorable_move_percent == 0.35
    assert config.buffer_percent == 0.10
