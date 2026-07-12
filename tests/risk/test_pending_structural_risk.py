import pytest

from app.execution.sl_tp_profile import EffectiveSlTp
from app.risk.models import TradePlan
from app.risk.trade_cost_model import TradeCostConfig
from tests.risk.test_risk_manager import (
    build_risk_manager,
    buy_signal,
    snapshot,
)


def pending_structural_sl_tp(
    *,
    stop_loss_percent=1.0,
    take_profit_percent=2.0,
    valid=True,
    reason=None,
    baseline_stop_loss_percent=0.5,
):
    return EffectiveSlTp(
        stop_loss_percent=stop_loss_percent,
        take_profit_percent=take_profit_percent,
        atr_percent=0.5,
        mode='dynamic',
        source='pending_structural',
        metadata={
            'structural_stop_valid': valid,
            'structural_stop_reason': reason,
            'constant_risk_baseline_stop_loss_percent': (
                baseline_stop_loss_percent
            ),
        },
    )


def test_pending_structural_stop_reduces_position_to_keep_risk_constant():
    risk_manager = build_risk_manager(
        trade_cost=TradeCostConfig(include_spread_cost=False),
    )

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL', bid=100.0, ask=100.0, last=100.0),
        account_equity=100.0,
        session_key='US',
        effective_sl_tp=pending_structural_sl_tp(
            stop_loss_percent=1.0,
            baseline_stop_loss_percent=0.5,
        ),
    )

    assert plan.approved
    assert plan.amount == 20.0
    assert plan.effective_stop_loss_percent == 1.0


def test_pending_structural_stop_rejects_invalid_invalidation():
    risk_manager = build_risk_manager()

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
        session_key='US',
        effective_sl_tp=pending_structural_sl_tp(
            valid=False,
            reason='invalid_buy_structural_stop',
        ),
    )

    assert not plan.approved
    assert plan.reason == 'invalid_buy_structural_stop'


def test_pending_structural_stop_rejects_insufficient_reward_to_risk():
    risk_manager = build_risk_manager()

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
        session_key='US',
        effective_sl_tp=pending_structural_sl_tp(
            stop_loss_percent=1.0,
            take_profit_percent=0.5,
        ),
    )

    assert not plan.approved
    assert plan.reason == 'structural_reward_to_risk_too_low'


def test_pending_structural_stop_rejects_distance_above_profile_maximum():
    risk_manager = build_risk_manager(max_stop_loss_percent=1.0)

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
        session_key='US',
        effective_sl_tp=pending_structural_sl_tp(
            stop_loss_percent=1.5,
            take_profit_percent=3.0,
        ),
    )

    assert not plan.approved
    assert plan.reason == 'structural_stop_too_wide'


def test_buy_structural_stop_keeps_absolute_invalidation_after_fill():
    risk_manager = build_risk_manager()
    plan = TradePlan(
        approved=True,
        reason='pending_confirmation',
        symbol='AAPL',
        side='BUY',
        stop_loss=99.0,
        take_profit=102.0,
        sl_tp_source='pending_structural',
        effective_stop_loss_percent=1.0,
        effective_take_profit_percent=2.0,
    )

    adjusted = risk_manager.adjust_trade_plan_to_entry_price(
        trade_plan=plan,
        entry_price=101.0,
    )

    assert adjusted.stop_loss == 99.0
    assert adjusted.take_profit == 103.02
    assert adjusted.effective_stop_loss_percent == 1.9802


def test_sell_structural_stop_keeps_absolute_invalidation_after_fill():
    risk_manager = build_risk_manager()
    plan = TradePlan(
        approved=True,
        reason='pending_confirmation',
        symbol='AAPL',
        side='SELL',
        stop_loss=101.0,
        take_profit=98.0,
        sl_tp_source='pending_structural',
        effective_stop_loss_percent=1.0,
        effective_take_profit_percent=2.0,
    )

    adjusted = risk_manager.adjust_trade_plan_to_entry_price(
        trade_plan=plan,
        entry_price=99.0,
    )

    assert adjusted.stop_loss == 101.0
    assert adjusted.take_profit == 97.02
    assert adjusted.effective_stop_loss_percent == 2.0202


def test_structural_fill_crossing_stop_is_rejected():
    risk_manager = build_risk_manager()
    plan = TradePlan(
        approved=True,
        reason='pending_confirmation',
        symbol='AAPL',
        side='BUY',
        stop_loss=99.0,
        take_profit=102.0,
        sl_tp_source='pending_structural',
        effective_stop_loss_percent=1.0,
        effective_take_profit_percent=2.0,
    )

    with pytest.raises(ValueError, match='crossed structural stop level'):
        risk_manager.adjust_trade_plan_to_entry_price(
            trade_plan=plan,
            entry_price=98.5,
        )
