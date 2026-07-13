from app.instruments.models import AssetClass
from app.risk.profiles import DEFAULT_RISK_PROFILES


def test_default_risk_profiles_use_balanced_trade_cooldown():
    cooldown = DEFAULT_RISK_PROFILES[AssetClass.EQUITY_US].trade_cooldown

    assert cooldown.after_take_profit_minutes == 30
    assert cooldown.after_stop_loss_minutes == 45
    assert cooldown.after_manual_close_minutes == 15
    assert cooldown.after_unknown_close_minutes == 15
