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


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        symbol='AMD',
        bid=100.0,
        ask=100.05,
        last=100.02,
        timestamp=datetime.now(timezone.utc),
    )


def _candle() -> Candle:
    now = datetime.now(timezone.utc)
    return Candle(
        symbol='AMD',
        timeframe_seconds=60,
        open=99.5,
        high=100.2,
        low=99.4,
        close=100.0,
        volume=None,
        opened_at=now,
        closed_at=now,
    )


def _candidate(*, side: str = 'BUY', close_position_percent: float = 88.0) -> TradeCandidate:
    return TradeCandidate(
        symbol='AMD',
        snapshot=_snapshot(),
        candle=_candle(),
        signal=Signal(
            action=side,
            confidence=0.8,
            reason='trend_bullish_breakout' if side == 'BUY' else 'trend_bearish_breakdown',
            metadata={
                'market_regime': 'TRENDING',
                'trend_strength_percent': 0.25,
                'close_position_percent': close_position_percent,
            },
        ),
        score=130.0,
        rank_reason='score=130 | setup_quality=0.8',
    )


def _economics() -> CandidateEconomics:
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
    tp_to_atr_ratio: float | None = 1.5,
    tp_to_snapshot_momentum_ratio: float | None = 3.0,
    cost_to_tp_ratio: float = 0.20,
    movement_consumed_percent: float | None = 0.40,
    runway_score: float = 92.0,
) -> TpFeasibilityAnalysis:
    return TpFeasibilityAnalysis(
        effective_take_profit_percent=0.60,
        effective_stop_loss_percent=0.40,
        atr_percent=0.40,
        snapshot_momentum_percent=0.30,
        directional_snapshot_momentum_percent=0.30,
        session_move_percent=0.70,
        directional_session_move_percent=0.70,
        tp_to_atr_ratio=tp_to_atr_ratio,
        tp_to_snapshot_momentum_ratio=tp_to_snapshot_momentum_ratio,
        required_net_move_percent=0.36,
        cost_to_tp_ratio=cost_to_tp_ratio,
        reward_to_risk_ratio=1.50,
        net_reward_to_risk_ratio=0.80,
        sl_tp_mode='dynamic',
        sl_tp_source='atr',
        distance_to_trade_extreme_percent=0.20,
        movement_consumed_percent=movement_consumed_percent,
        runway_score=runway_score,
        raw_runway_score=runway_score,
        score_before_tp_feasibility=130.0,
        score_after_tp_penalty=130.0,
        tp_feasibility_penalty=0.0,
        raw_tp_feasibility_penalty=0.0,
        score_cap=None,
        adjusted_score=130.0,
        tp_feasibility_hard_rejection_reason=None,
        readiness=CandidateReadiness.TRADABLE_NOW,
        readiness_reason='tp_feasibility_ready',
        penalty_components=(),
        cap_components=(),
        hard_rejection_components=(),
        reason_components=('tp_atr_ok', 'tp_momentum_ok', 'cost_to_tp_ok', 'runway_ok'),
    )


def test_tp_probability_decreases_when_tp_is_far_and_move_consumed() -> None:
    estimator = TpBeforeSlProbabilityEstimator()
    evaluated_candidate = EvaluatedTradeCandidate(
        candidate=_candidate(),
        economics=_economics(),
        tp_feasibility=_feasibility(),
    )

    strong = estimator.estimate(
        evaluated_candidate=evaluated_candidate,
        tp_feasibility=_feasibility(),
    )
    weak = estimator.estimate(
        evaluated_candidate=evaluated_candidate,
        tp_feasibility=_feasibility(
            tp_to_atr_ratio=6.5,
            tp_to_snapshot_momentum_ratio=12.5,
            cost_to_tp_ratio=0.70,
            movement_consumed_percent=2.20,
            runway_score=30.0,
        ),
    )

    assert strong.tp_before_sl_probability > weak.tp_before_sl_probability
    assert weak.probability_band in {'VERY_LOW', 'LOW', 'MEDIUM'}


def test_candidate_tp_probability_evaluator_logs_probability_without_changing_score() -> None:
    candidate = _candidate()
    evaluated_candidate = EvaluatedTradeCandidate(
        candidate=candidate,
        economics=_economics(),
        tp_feasibility=_feasibility(),
    )

    updated = CandidateTpProbabilityEvaluator().evaluate(evaluated_candidate)

    assert updated.candidate.score == candidate.score
    assert updated.candidate.tp_before_sl_probability is not None
    assert updated.candidate.tp_before_sl_probability_band is not None
    assert updated.candidate.tp_probability_model_version == 'heuristic_v1'
    assert 'tp_before_sl_probability=' in updated.candidate.rank_reason
    assert updated.tp_probability is not None


def test_sell_close_quality_is_directional() -> None:
    candidate = _candidate(side='SELL', close_position_percent=12.0)
    evaluated_candidate = EvaluatedTradeCandidate(
        candidate=candidate,
        economics=_economics(),
        tp_feasibility=_feasibility(),
    )

    estimate = TpBeforeSlProbabilityEstimator().estimate(
        evaluated_candidate=evaluated_candidate,
        tp_feasibility=_feasibility(),
    )

    assert estimate.component_scores['close_quality_score'] > 90.0
