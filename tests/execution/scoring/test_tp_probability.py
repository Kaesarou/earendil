from datetime import datetime, timezone
from types import SimpleNamespace

from app.execution.candidate_economics import (
    CandidateEconomics,
    EvaluatedTradeCandidate,
)
from app.execution.candidate_readiness import CandidateReadiness
from app.execution.scoring.tp_feasibility import TpFeasibilityAnalysis
from app.execution.scoring.tp_probability import (
    CandidateTpProbabilityEvaluator,
    TpBeforeSlProbabilityEstimator,
)
from app.execution.trade_candidate import TradeCandidate
from app.instruments.models import AssetClass
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal


def _candidate(*, asset_class=AssetClass.EQUITY_US, side='BUY', close=88.0):
    now = datetime.now(timezone.utc)
    return TradeCandidate(
        symbol='AMD',
        snapshot=MarketSnapshot('AMD', 100.0, 100.05, 100.02, now),
        candle=Candle(
            'AMD', 60, 99.5, 100.2, 99.4, 100.0, None, now, now
        ),
        signal=Signal(
            side,
            0.8,
            'test',
            metadata={
                'market_regime': 'TRENDING',
                'trend_strength_percent': 0.25,
                'close_position_percent': close,
            },
        ),
        score=130.0,
        rank_reason='score=130',
        market_context=SimpleNamespace(asset_class=asset_class),
    )


def _economics():
    return CandidateEconomics(
        position_value=500.0,
        expected_gross_profit=3.0,
        expected_net_profit=2.2,
        expected_net_profit_percent=0.44,
        estimated_total_cost=0.8,
        estimated_total_cost_percent=0.16,
        min_expected_net_profit_percent=0.10,
        required_min_expected_net_profit_amount=0.5,
        effective_take_profit_percent=0.60,
        effective_stop_loss_percent=0.40,
        cost_to_tp_ratio=0.20,
        reward_to_risk_ratio=1.50,
        net_reward_to_risk_ratio=0.80,
    )


def _feasibility(
    *,
    score=92.0,
    tp_to_atr_ratio=1.5,
    tp_to_momentum_ratio=3.0,
    cost_to_tp_ratio=0.20,
    movement_consumed=0.40,
):
    return TpFeasibilityAnalysis(
        effective_take_profit_percent=0.60,
        effective_stop_loss_percent=0.40,
        atr_percent=0.40,
        snapshot_momentum_percent=0.30,
        directional_snapshot_momentum_percent=0.30,
        session_move_percent=0.70,
        directional_session_move_percent=0.70,
        tp_to_atr_ratio=tp_to_atr_ratio,
        tp_to_snapshot_momentum_ratio=tp_to_momentum_ratio,
        required_net_move_percent=0.36,
        cost_to_tp_ratio=cost_to_tp_ratio,
        reward_to_risk_ratio=1.50,
        net_reward_to_risk_ratio=0.80,
        sl_tp_mode='dynamic',
        sl_tp_source='dynamic_raw',
        distance_to_trade_extreme_percent=0.20,
        movement_consumed_percent=movement_consumed,
        feasibility_score=score,
        component_scores={
            'tp_vs_atr': score,
            'tp_vs_momentum': score,
            'cost_vs_tp': score,
            'movement_remaining': score,
        },
        score_before_tp_feasibility=130.0,
        score_contribution=0.0,
        adjusted_score=130.0,
        tp_feasibility_hard_rejection_reason=None,
        readiness=CandidateReadiness.TRADABLE_NOW,
        readiness_reason='entry_decision_required',
        hard_rejection_components=(),
        reason_components=('continuous_score',),
    )


def _evaluated(candidate, feasibility=None):
    return EvaluatedTradeCandidate(
        candidate=candidate,
        economics=_economics(),
        tp_feasibility=feasibility or _feasibility(),
    )


def test_probability_decreases_when_feasibility_deteriorates():
    estimator = TpBeforeSlProbabilityEstimator()
    evaluated = _evaluated(_candidate())
    strong = estimator.estimate(
        evaluated_candidate=evaluated,
        tp_feasibility=_feasibility(score=92.0),
    )
    weak = estimator.estimate(
        evaluated_candidate=evaluated,
        tp_feasibility=_feasibility(
            score=20.0,
            tp_to_atr_ratio=6.5,
            tp_to_momentum_ratio=12.5,
            cost_to_tp_ratio=0.70,
            movement_consumed=2.20,
        ),
    )

    assert strong.raw_probability > weak.raw_probability
    assert strong.tp_before_sl_probability > weak.tp_before_sl_probability
    assert strong.net_expected_value_percent > weak.net_expected_value_percent


def test_asset_calibration_is_applied_after_raw_probability():
    estimator = TpBeforeSlProbabilityEstimator()
    us = estimator.estimate(
        evaluated_candidate=_evaluated(_candidate(asset_class=AssetClass.EQUITY_US)),
        tp_feasibility=_feasibility(),
    )
    eu = estimator.estimate(
        evaluated_candidate=_evaluated(_candidate(asset_class=AssetClass.EQUITY_EU)),
        tp_feasibility=_feasibility(),
    )

    assert us.raw_probability == eu.raw_probability
    assert eu.tp_before_sl_probability > us.tp_before_sl_probability
    assert us.calibration_base_rate == 0.41
    assert eu.calibration_base_rate == 0.56


def test_candidate_probability_persists_raw_calibrated_and_ev_without_score_change():
    candidate = _candidate()
    updated = CandidateTpProbabilityEvaluator().evaluate(
        _evaluated(candidate)
    )

    assert updated.candidate.score == candidate.score
    assert updated.candidate.raw_tp_before_sl_probability is not None
    assert updated.candidate.tp_before_sl_probability is not None
    assert updated.candidate.tp_probability_model_version == 'heuristic_v3'
    assert updated.candidate.break_even_probability is not None
    assert updated.candidate.net_expected_value_percent is not None
    assert updated.candidate.probability_edge is not None
    assert 'raw_tp_before_sl_probability=' in updated.candidate.rank_reason


def test_break_even_probability_includes_costs_on_losing_side():
    estimate = TpBeforeSlProbabilityEstimator().estimate(
        evaluated_candidate=_evaluated(_candidate()),
        tp_feasibility=_feasibility(),
    )
    expected = (0.40 + 0.16) / (0.44 + 0.40 + 0.16)
    assert estimate.break_even_probability == round(expected, 4)
    assert estimate.probability_edge == round(
        estimate.tp_before_sl_probability - expected,
        4,
    )


def test_sell_close_quality_is_directional():
    estimate = TpBeforeSlProbabilityEstimator().estimate(
        evaluated_candidate=_evaluated(
            _candidate(side='SELL', close=12.0)
        ),
        tp_feasibility=_feasibility(),
    )
    assert estimate.component_scores['close_quality_score'] > 90.0
