from app.risk.models import TradePlan
from app.risk.risk_manager import RiskManager


def test_buy_structural_stop_is_preserved_after_worse_fill():
    manager = RiskManager.__new__(RiskManager)
    plan = TradePlan(
        approved=True,
        reason='test',
        symbol='AMD',
        side='BUY',
        stop_loss=99.0,
        take_profit=100.8,
        sl_tp_source='pending_structural',
        effective_stop_loss_percent=1.0,
        effective_take_profit_percent=0.8,
    )

    adjusted = manager.adjust_trade_plan_to_entry_price(
        trade_plan=plan,
        entry_price=101.0,
    )

    assert adjusted.stop_loss == 99.0
    assert adjusted.take_profit == 101.808
    assert adjusted.effective_stop_loss_percent == 1.9802


def test_sell_structural_stop_is_preserved_after_worse_fill():
    manager = RiskManager.__new__(RiskManager)
    plan = TradePlan(
        approved=True,
        reason='test',
        symbol='AMD',
        side='SELL',
        stop_loss=101.0,
        take_profit=99.2,
        sl_tp_source='pending_structural',
        effective_stop_loss_percent=1.0,
        effective_take_profit_percent=0.8,
    )

    adjusted = manager.adjust_trade_plan_to_entry_price(
        trade_plan=plan,
        entry_price=99.0,
    )

    assert adjusted.stop_loss == 101.0
    assert adjusted.take_profit == 98.208
    assert adjusted.effective_stop_loss_percent == 2.0202


def test_non_structural_stop_still_moves_with_fill_price():
    manager = RiskManager.__new__(RiskManager)
    plan = TradePlan(
        approved=True,
        reason='test',
        symbol='AMD',
        side='BUY',
        stop_loss=99.0,
        take_profit=100.8,
        sl_tp_source='dynamic_raw',
        effective_stop_loss_percent=1.0,
        effective_take_profit_percent=0.8,
    )

    adjusted = manager.adjust_trade_plan_to_entry_price(
        trade_plan=plan,
        entry_price=101.0,
    )

    assert adjusted.stop_loss == 99.99
    assert adjusted.take_profit == 101.808
