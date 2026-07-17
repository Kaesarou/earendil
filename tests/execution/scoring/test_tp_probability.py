from datetime import datetime, timezone

from app.execution.candidate_economics import CandidateEconomics, EvaluatedTradeCandidate
from app.execution.candidate_readiness import CandidateReadiness
from app.execution.scoring.tp_feasibility import TpFeasibilityAnalysis
from app.execution.scoring.tp_probability import (
    CandidateTpProbabilityEvaluator,
    TpBeforeSlProbabilityEstimator,
)
from app.execution.trade_candidate import TradeCandidate
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal


def _candidate(*, side='BUY', close=None, context_score=0.0, mtf_score=0.0):
    now = datetime.now(timezone.utc)
    directional_close = (12.0 if side == 'SELL' else 88.0) if close is None else close
    return TradeCandidate(
        symbol='AMD',
        snapshot=MarketSnapshot('AMD', 100.0, 100.05, 100.02, now),
        candle=Candle('AMD', 60, 99.5, 100.2, 99.4, 100.0, None, now, now),
        signal=Signal(
            side,
            0.8,
            'test',
            metadata={
                'market_regime': 'TRENDING',
                'trend_strength_percent': 0.25,
                'close_position_percent': directional_close,
            },
        ),
        score=130.0,
        rank_reason='score=130',
        market_context_score=context_score,
        multi_timeframe_score=mtf_score,
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
    source='us_intraday_fixed_v1',
    tp_to_atr_ratio=1.5,
    tp_to_momentum_ratio=3.0,
    cost_to_tp_ratio=0.20,
    movement_consumed=0.40,
    movement_consumed_to_tp_ratio=0.67,
    freshness_score=88.0,
):
    return TpFeasibilityAnalysis(
        effective_take_profit_percent=0.60,
        effective_stop_loss_percent=0.40,
        atr_percent=0.40,
        snapshot_momentum_percent=0.30,
        directional_snapshot_momentum_percent=0.30,
        session_move_percent=0.40,
        directional_session_move_percent=0.40,
        tp_to_atr_ratio=tp_to_atr_ratio,
        tp_to_snapshot_momentum_ratio=tp_to_momentum_ratio,
        required_net_move_percent=0.36,
        cost_to_tp_ratio=cost_to_tp_ratio,
        reward_to_risk_ratio=1.50,
        net_reward_to_risk_ratio=0.80,
        sl_tp_mode='fixed',
        sl_tp_source=source,
        distance_to_trade_extreme_percent=0.20,
        movement_consumed_percent=movement_consumed,
        movement_consumed_to_tp_ratio=movement_consumed_to_tp_ratio,
        entry_freshness_score=freshness_score,
        feasibility_score=80.0,
        component_scores={
            'tp_vs_atr': 80.0,
            'tp_vs_momentum': 80.0,
            'cost_vs_tp': 80.0,
            'entry_freshness': freshness_score,
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


def test_probability_decreases_when_direct_tp_inputs_deteriorate():
    estimator = TpBeforeSlProbabilityEstimator()
    candidate = _candidate()
    strong = estimator.estimate(
        evaluated_candidate=_evaluated(candidate),
        tp_feasibility=_feasibility(),
    )
    weak = estimator.estimate(
        evaluated_candidate=_evaluated(candidate),
        tp_feasibility=_feasibility(
            tp_to_atr_ratio=6.5,
            tp_to_momentum_ratio=12.5,
            cost_to_tp_ratio=0.70,
            movement_consumed=2.20,
            movement_consumed_to_tp_ratio=3.67,
            freshness_score=0.0,
        ),
    )
    assert strong.raw_probability > weak.raw_probability
    assert strong.tp_before_sl_probability > weak.tp_before_sl_probability
    assert strong.net_expected_value_percent > weak.net_expected_value_percent
    assert 'feasibility_score' not in strong.component_scores


def test_profile_and_side_calibration_is_applied_after_raw_probability():
    estimator = TpBeforeSlProbabilityEstimator()
    us_buy = estimator.estimate(
        evaluated_candidate=_evaluated(_candidate(side='BUY')),
        tp_feasibility=_feasibility(source='us_intraday_fixed_v1'),
    )
    us_sell = estimator.estimate(
        evaluated_candidate=_evaluated(_candidate(side='SELL')),
        tp_feasibility=_feasibility(source='us_intraday_fixed_v1'),
    )
    eu_buy = estimator.estimate(
        evaluated_candidate=_evaluated(_candidate(side='BUY')),
        tp_feasibility=_feasibility(source='eu_trend_buy_v1'),
    )
    assert us_buy.raw_probability == us_sell.raw_probability == eu_buy.raw_probability
    assert us_buy.calibration_profile_key == 'us_intraday_fixed_v1:BUY'
    assert us_sell.calibration_profile_key == 'us_intraday_fixed_v1:SELL'
    assert eu_buy.calibration_profile_key == 'eu_trend_buy_v1:BUY'
    assert us_buy.calibration_base_rate == 0.45
    assert us_sell.calibration_base_rate == 0.18
    assert eu_buy.calibration_base_rate == 0.33
    assert us_buy.tp_before_sl_probability > eu_buy.tp_before_sl_probability > us_sell.tp_before_sl_probability


def test_context_and_ready_mtf_are_probability_inputs():
    estimator = TpBeforeSlProbabilityEstimator()
    weak = estimator.estimate(
        evaluated_candidate=_evaluated(_candidate(context_score=-15.0, mtf_score=-10.0)),
        tp_feasibility=_feasibility(),
    )
    strong = estimator.estimate(
        evaluated_candidate=_evaluated(_candidate(context_score=15.0, mtf_score=10.0)),
        tp_feasibility=_feasibility(),
    )
    assert strong.raw_probability > weak.raw_probability
    assert strong.component_scores['market_context_score'] == 100.0
    assert strong.component_scores['multi_timeframe_score'] == 100.0


def test_candidate_probability_persists_v4_evidence_without_score_change():
    candidate = _candidate()
    updated = CandidateTpProbabilityEvaluator().evaluate(_evaluated(candidate))
    assert updated.candidate.score == candidate.score
    assert updated.candidate.tp_probability_model_version == 'heuristic_v4'
    assert updated.tp_probability.calibration_profile_key == 'us_intraday_fixed_v1:BUY'
    assert updated.candidate.net_expected_value_percent is not None
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
        evaluated_candidate=_evaluated(_candidate(side='SELL', close=12.0)),
        tp_feasibility=_feasibility(),
    )
    assert estimate.component_scores['close_quality_score'] > 90.0
