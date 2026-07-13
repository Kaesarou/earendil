from app.strategies.balanced_strategy_config import BalancedStrategyConfig


def test_crypto_stale_position_config_is_enabled():
    config = BalancedStrategyConfig().crypto.risk.stale_position

    assert config.enabled
    assert config.max_age_minutes == 60
    assert config.min_favorable_move_percent == 0.80
    assert config.buffer_percent == 0.0


def test_equity_us_stale_position_config_is_enabled():
    config = BalancedStrategyConfig().equity_us.risk.stale_position

    assert config.enabled
    assert config.max_age_minutes == 60
    assert config.min_favorable_move_percent == 0.35
    assert config.buffer_percent == 0.10


def test_equity_eu_stale_position_config_is_enabled():
    config = BalancedStrategyConfig().equity_eu.risk.stale_position

    assert config.enabled
    assert config.max_age_minutes == 75
    assert config.min_favorable_move_percent == 0.35
    assert config.buffer_percent == 0.10
