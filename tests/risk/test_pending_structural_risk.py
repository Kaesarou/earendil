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
        mode='fixed',
        source='pending_structural',
        metadata={
            'structural_stop_valid': valid,
            'structural_stop_reason': reason,
            'constant_risk_baseline_stop_loss_percent': baseline_stop_loss_percent,
            'baseline_sl_tp_source': 'us_test_fixed_v1',
        },
    )


def test_pending_structural_stop_reduces_position_to_keep_risk_constant():
    manager = build_risk_manager(
        trade_cost=TradeCostConfig(include_spread_cost=False),
    )
    plan = manager.evaluate(
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
    assert plan.profile_key == 'us_test_fixed_v1'
    assert plan.effective_stop_loss_percent == 1.0


def test_pending_structural_stop_rejects_invalid_invalidation():
    plan = build_risk_manager().evaluate(
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
    plan = build_risk_manager().evaluate(
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


def test_pending_structural_stop_rejects_distance_above_confirmation_maximum():
    plan = build_risk_manager().evaluate(
        signal=buy_signal(),
        snapshot=snapshot('AAPL'),
        account_equity=100.0,
        session_key='US',
        effective_sl_tp=pending_structural_sl_tp(
            stop_loss_percent=2.0,
            take_profit_percent=3.0,
        ),
    )
    assert not plan.approved
    assert plan.reason == 'structural_stop_too_wide'


@pytest.mark.parametrize(
    ('side', 'entry_price', 'stop_loss', 'take_profit', 'expected_tp', 'expected_sl_percent'),
    [
        ('BUY', 101.0, 99.0, 102.0, 103.02, 1.9802),
        ('SELL', 99.0, 101.0, 98.0, 97.02, 2.0202),
    ],
)
def test_structural_stop_keeps_absolute_invalidation_after_fill(
    side,
    entry_price,
    stop_loss,
    take_profit,
    expected_tp,
    expected_sl_percent,
):
    plan = TradePlan(
        approved=True,
        reason='pending_confirmation',
        symbol='AAPL',
        side=side,
        stop_loss=stop_loss,
        take_profit=take_profit,
        sl_tp_source='pending_structural',
        effective_stop_loss_percent=1.0,
        effective_take_profit_percent=2.0,
    )
    adjusted = build_risk_manager().adjust_trade_plan_to_entry_price(
        trade_plan=plan,
        entry_price=entry_price,
    )
    assert adjusted.stop_loss == stop_loss
    assert adjusted.take_profit == expected_tp
    assert adjusted.effective_stop_loss_percent == expected_sl_percent


def test_structural_fill_crossing_stop_is_rejected():
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
        build_risk_manager().adjust_trade_plan_to_entry_price(
            trade_plan=plan,
            entry_price=98.5,
        )
