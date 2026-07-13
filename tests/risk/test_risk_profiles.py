from app.strategies.balanced_strategy_config import BalancedStrategyConfig


def test_balanced_profile_uses_expected_trade_cooldown():
    cooldown = BalancedStrategyConfig().equity_us.risk.trade_cooldown

    assert cooldown.after_take_profit_minutes == 30
    assert cooldown.after_stop_loss_minutes == 45
    assert cooldown.after_manual_close_minutes == 15
    assert cooldown.after_unknown_close_minutes == 15
