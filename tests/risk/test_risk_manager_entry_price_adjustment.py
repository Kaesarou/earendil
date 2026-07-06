import pytest

from app.risk.models import TradePlan
from app.risk.risk_manager import RiskManager


def plan(side: str = 'BUY') -> TradePlan:
    return TradePlan(
        approved=True,
        reason='test',
        symbol='AAPL',
        side=side,
        amount=100.0,
        stop_loss=99.0,
        take_profit=102.0,
        effective_stop_loss_percent=0.8,
        effective_take_profit_percent=1.4,
        estimated_total_cost_percent=0.3,
        breakeven_stop_enabled=True,
        breakeven_trigger_percent=1.7,
        breakeven_buffer_percent=0.3,
        trailing_stop_enabled=True,
        trailing_stop_trigger_percent=1.0,
        trailing_stop_distance_percent=0.4,
        stale_position_enabled=True,
        stale_position_max_age_minutes=60,
        stale_position_min_favorable_move_percent=0.35,
        stale_position_buffer_percent=0.1,
    )


def test_adjust_buy_trade_plan_to_entry_price():
    original = plan('BUY')

    adjusted = RiskManager.adjust_trade_plan_to_entry_price(None, trade_plan=original, entry_price=238.0)

    assert adjusted.stop_loss == 236.096
    assert adjusted.take_profit == 241.332
    assert adjusted.estimated_total_cost_percent == original.estimated_total_cost_percent
    assert adjusted.breakeven_stop_enabled == original.breakeven_stop_enabled
    assert adjusted.trailing_stop_enabled == original.trailing_stop_enabled
    assert adjusted.stale_position_enabled == original.stale_position_enabled


def test_adjust_sell_trade_plan_to_entry_price():
    adjusted = RiskManager.adjust_trade_plan_to_entry_price(None, trade_plan=plan('SELL'), entry_price=238.0)

    assert adjusted.stop_loss == 239.904
    assert adjusted.take_profit == 234.668


def test_adjust_trade_plan_rejects_invalid_input():
    with pytest.raises(ValueError):
        RiskManager.adjust_trade_plan_to_entry_price(None, trade_plan=TradePlan(approved=False, reason='nope'), entry_price=238.0)
    with pytest.raises(ValueError):
        RiskManager.adjust_trade_plan_to_entry_price(None, trade_plan=plan(), entry_price=0.0)
    with pytest.raises(ValueError):
        RiskManager.adjust_trade_plan_to_entry_price(None, trade_plan=TradePlan(approved=True, reason='x', side='HOLD'), entry_price=238.0)
