import pytest

from app.instruments.models import AssetClass
from app.risk.profiles import risk_profiles_for_aggressiveness


def test_balanced_risk_profiles_use_balanced_trade_cooldown():
    profiles = risk_profiles_for_aggressiveness('balanced')

    cooldown = profiles[AssetClass.EQUITY_US].trade_cooldown

    assert cooldown.after_take_profit_minutes == 30
    assert cooldown.after_stop_loss_minutes == 45
    assert cooldown.after_manual_close_minutes == 15
    assert cooldown.after_unknown_close_minutes == 15


def test_aggressive_risk_profiles_use_aggressive_trade_cooldown():
    profiles = risk_profiles_for_aggressiveness('aggressive')

    cooldown = profiles[AssetClass.EQUITY_US].trade_cooldown

    assert cooldown.after_take_profit_minutes == 15
    assert cooldown.after_stop_loss_minutes == 30
    assert cooldown.after_manual_close_minutes == 10
    assert cooldown.after_unknown_close_minutes == 10


def test_unknown_risk_aggressiveness_is_rejected():
    with pytest.raises(ValueError):
        risk_profiles_for_aggressiveness('reckless')
