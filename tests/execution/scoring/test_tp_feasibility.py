from datetime import datetime, timezone

from app.execution.candidate_economics import CandidateEconomics, EvaluatedTradeCandidate
from app.execution.scoring.tp_feasibility import CandidateTpFeasibilityEvaluator, TpFeasibilityAnalyzer
from app.execution.trade_candidate import TradeCandidate
from app.instruments.models import AssetClass, RiskProfile, TpFeasibilityConfig
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal

SESSION_KEY = 'test-session'


def snapshot(symbol: str = 'TEST') -> MarketSnapshot:
    return MarketSnapshot(symbol=symbol, bid=99.9, ask=100.1, last=100.0, timestamp=datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc))


def candle(symbol: str = 'TEST') -> Candle:
    timestamp = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    return Candle(symbol=symbol, timeframe_seconds=60, open=99.0, high=101.0, low=98.5, close=100.0, volume=None, opened_at=timestamp, closed_at=timestamp)


def signal(side: str = 'BUY', metadata: dict | None = None) -> Signal:
    return Signal(action=side, confidence=0.8, reason='test_signal', metadata=metadata or {})


def candidate(side: str = 'BUY', score: float = 150.0, metadata: dict | None = None, entry_quality_metadata: dict | None = None) -> TradeCandidate:
    return TradeCandidate(
        symbol='TEST',
        snapshot=snapshot(),
        candle=candle(),
        signal=signal(side, metadata),
        score=score,
        rank_reason='test_score',
        session_key=SESSION_KEY,
        base_score=score,
        entry_quality_metadata=entry_quality_metadata or {'distance_to_recent_high_percent': 1.0, 'distance_to_recent_low_percent': 1.0},
    )


def economics(cost_percent: float = 0.15) -> CandidateEconomics:
    return CandidateEconomics(
        position_value=1000.0,
        expected_gross_profit=10.0,
        expected_net_profit=10.0 - cost_percent * 10,
        expected_net_profit_percent=1.0 - cost_percent,
        estimated_total_cost=cost_percent * 10,
        estimated_total_cost_percent=cost_percent,
        min_expected_net_profit_percent=0.10,
        required_min_expected_net_profit_amount=1.0,
    )


def risk_profile(take_profit_percent: float = 1.0, stop_loss_percent: float = 0.8, config: TpFeasibilityConfig | None = None) -> RiskProfile:
    return RiskProfile(
        asset_class=AssetClass.EQUITY_US,
        max_position_size_percent=1.0,
        stop_loss_percent=stop_loss_percent,
        take_profit_percent=take_profit_percent,
        force_close_enabled=False,
        force_close_hour=21,
        force_close_minute=55,
        max_spread_percent=1.0,
        min_move_spread_ratio=0.0,
        dynamic_sl_tp_enabled=False,
        stop_loss_atr_multiplier=1.0,
        take_profit_atr_multiplier=2.0,
        min_stop_loss_percent=0.0,
        max_stop_loss_percent=2.0,
        min_take_profit_percent=0.0,
        max_take_profit_percent=3.0,
        tp_feasibility=config or TpFeasibilityConfig(),
    )


def evaluated(side: str = 'BUY', score: float = 150.0, metadata: dict | None = None, cost_percent: float = 0.15, entry_quality_metadata: dict | None = None) -> EvaluatedTradeCandidate:
    return EvaluatedTradeCandidate(
        candidate=candidate(side=side, score=score, metadata=metadata, entry_quality_metadata=entry_quality_metadata),
        economics=economics(cost_percent),
    )


def test_tp_feasibility_easy_tp_has_low_penalty():
    analysis = TpFeasibilityAnalyzer().analyze(
        evaluated_candidate=evaluated(metadata={'atr_percent': 0.8, 'snapshot_momentum_percent': 0.4, 'session_move_percent': 0.3}),
        risk_profile=risk_profile(take_profit_percent=1.0),
    )

    assert analysis.tp_feasibility_penalty == 0.0
    assert analysis.score_cap is None
    assert analysis.tp_feasibility_rejection_reason is None
    assert analysis.runway_score == 100.0


def test_tp_feasibility_rejects_tp_too_far_vs_atr():
    analysis = TpFeasibilityAnalyzer().analyze(
        evaluated_candidate=evaluated(metadata={'atr_percent': 0.25, 'snapshot_momentum_percent': 0.5, 'session_move_percent': 0.3}),
        risk_profile=risk_profile(take_profit_percent=1.6),
    )

    assert analysis.tp_to_atr_ratio == 6.4
    assert analysis.tp_feasibility_rejection_reason == 'candidate_selection_tp_feasibility_tp_too_far_vs_atr'
    assert 'tp_too_far_vs_atr_reject' in analysis.reason_components


def test_tp_feasibility_caps_when_snapshot_momentum_is_opposite():
    analysis = TpFeasibilityAnalyzer().analyze(
        evaluated_candidate=evaluated(side='BUY', metadata={'atr_percent': 0.8, 'snapshot_momentum_percent': -0.1, 'session_move_percent': 0.3}),
        risk_profile=risk_profile(take_profit_percent=1.0),
    )

    assert analysis.directional_snapshot_momentum_percent == -0.1
    assert analysis.score_cap == 95.0
    assert 'opposite_snapshot_momentum' in analysis.reason_components


def test_tp_feasibility_rejects_costs_too_high_vs_tp():
    analysis = TpFeasibilityAnalyzer().analyze(
        evaluated_candidate=evaluated(metadata={'atr_percent': 1.0, 'snapshot_momentum_percent': 0.5, 'session_move_percent': 0.3}, cost_percent=1.1),
        risk_profile=risk_profile(take_profit_percent=1.5),
    )

    assert analysis.cost_to_tp_ratio == 0.7333
    assert analysis.tp_feasibility_rejection_reason == 'candidate_selection_tp_feasibility_cost_to_tp_too_high'
    assert 'cost_to_tp_too_high_reject' in analysis.reason_components


def test_tp_feasibility_missing_data_is_safe_and_prudent():
    analysis = TpFeasibilityAnalyzer().analyze(
        evaluated_candidate=evaluated(metadata={}),
        risk_profile=risk_profile(take_profit_percent=1.0),
    )

    assert analysis.tp_feasibility_rejection_reason is None
    assert analysis.tp_feasibility_penalty == 24.0
    assert {'missing_atr', 'missing_snapshot_momentum', 'missing_session_move'}.issubset(set(analysis.reason_components))


def test_tp_feasibility_uses_sell_directional_momentum():
    good_sell = TpFeasibilityAnalyzer().analyze(
        evaluated_candidate=evaluated(side='SELL', metadata={'atr_percent': 0.8, 'snapshot_momentum_percent': -0.4, 'session_move_percent': -0.3}),
        risk_profile=risk_profile(take_profit_percent=1.0),
    )
    bad_sell = TpFeasibilityAnalyzer().analyze(
        evaluated_candidate=evaluated(side='SELL', metadata={'atr_percent': 0.8, 'snapshot_momentum_percent': 0.4, 'session_move_percent': -0.3}),
        risk_profile=risk_profile(take_profit_percent=1.0),
    )

    assert good_sell.directional_snapshot_momentum_percent == 0.4
    assert good_sell.tp_feasibility_penalty == 0.0
    assert bad_sell.directional_snapshot_momentum_percent == -0.4
    assert bad_sell.score_cap == 95.0


def test_candidate_tp_feasibility_evaluator_applies_score_cap():
    evaluated_candidate = evaluated(score=160.0, metadata={'atr_percent': 0.4, 'snapshot_momentum_percent': 0.5, 'session_move_percent': 0.3})

    result = CandidateTpFeasibilityEvaluator().evaluate(
        evaluated_candidate=evaluated_candidate,
        risk_profile=risk_profile(take_profit_percent=1.6),
    )

    assert result.candidate.score == 110.0
    assert result.candidate.tp_feasibility_score_cap == 110.0
    assert result.candidate.tp_feasibility_penalty == 22.0
    assert result.tp_feasibility is not None
    assert result.candidate.tp_feasibility_metadata['tp_to_atr_ratio'] == 4.0
