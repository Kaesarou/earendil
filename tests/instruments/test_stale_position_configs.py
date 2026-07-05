from app.instruments.models import AssetClass
from app.risk.profiles import risk_profiles_for_aggressiveness


def test_crypto_stale_position_config_is_enabled():
    profiles = risk_profiles_for_aggressiveness('balanced')

    config = profiles[AssetClass.CRYPTO].stale_position

    assert config.enabled
    assert config.max_age_minutes == 60
    assert config.min_favorable_move_percent == 0.80
    assert config.buffer_percent == 0.0


def test_equity_us_stale_position_config_is_enabled():
    profiles = risk_profiles_for_aggressiveness('balanced')

    config = profiles[AssetClass.EQUITY_US].stale_position

    assert config.enabled
    assert config.max_age_minutes == 60
    assert config.min_favorable_move_percent == 0.35
    assert config.buffer_percent == 0.10


def test_equity_eu_stale_position_config_is_enabled():
    profiles = risk_profiles_for_aggressiveness('balanced')

    config = profiles[AssetClass.EQUITY_EU].stale_position

    assert config.enabled
    assert config.max_age_minutes == 75
    assert config.min_favorable_move_percent == 0.35
    assert config.buffer_percent == 0.10
