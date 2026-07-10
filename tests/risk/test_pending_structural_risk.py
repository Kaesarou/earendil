from app.execution.sl_tp_profile import EffectiveSlTp
from app.risk.trade_cost_model import TradeCostConfig
from tests.risk.test_risk_manager import (
    build_risk_manager,
    buy_signal,
    evaluate,
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
