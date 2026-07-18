from dataclasses import replace
from datetime import datetime, timezone

from app.execution.candidate_economics import (
    CandidateEconomics,
    EvaluatedTradeCandidate,
)
from app.execution.candidate_ranking import build_trade_candidate
from app.execution.candidate_selector import (
    CandidateSelectionConfig,
    rank_evaluated_trade_candidates,
    select_evaluated_trade_candidates,
    select_trade_candidates,
)
from app.execution.trade_candidate import TradeCandidate
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal


TEST_SESSION_KEY = 'test-session'


def snapshot(
    symbol: str,
    bid: float = 99.9,
    ask: float = 100.1,
    last: float = 100.0,
) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        bid=bid,
        ask=ask,
        last=last,
        timestamp=datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc),
    )


def candle(symbol: str) -> Candle:
    timestamp = datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc)
    return Candle(
        symbol=symbol,
        timeframe_seconds=60,
        open=99.0,
        high=101.0,
        low=98.5,
        close=100.0,
        volume=None,
        opened_at=timestamp,
        closed_at=timestamp,
    )


def signal(
    session_move_percent: float = 1.0,
    trend_strength_percent: float = 0.3,
    atr_percent: float = 0.8,
    market_regime: str = 'TRENDING',
    noise_ratio: float = 0.4,
) -> Signal:
    return Signal(
        action='BUY',
        setup_quality=0.8,
        reason='test_signal',
        metadata={
            'session_move_percent': session_move_percent,
            'trend_strength_percent': trend_strength_percent,
            'breakout_percent': 0.2,
            'candle_range_percent': 0.4,
            'close_position_percent': 90.0,
            'atr_percent': atr_percent,
            'market_regime': market_regime,
            'regime_noise_ratio': noise_ratio,
        },
    )


def candidate(
    symbol: str,
    candidate_signal: Signal | None = None,
    candidate_snapshot: MarketSnapshot | None = None,
):
    return build_trade_candidate(
        symbol=symbol,
        snapshot=candidate_snapshot or snapshot(symbol),
        candle=candle(symbol),
        signal=candidate_signal or signal(),
        session_key=TEST_SESSION_KEY,
    )


def evaluated_candidate_with_profit(
    item: TradeCandidate,
) -> EvaluatedTradeCandidate:
    return EvaluatedTradeCandidate(
        candidate=item,
        economics=CandidateEconomics(
            position_value=100.0,
            expected_gross_profit=1.0,
            expected_net_profit=0.5,
            expected_net_profit_percent=0.5,
            estimated_total_cost=0.5,
            estimated_total_cost_percent=0.5,
            min_expected_net_profit_percent=0.10,
            required_min_expected_net_profit_amount=0.10,
        ),
    )


def test_candidate_selector_keeps_only_top_n_candidates():
    candidates = [
        candidate('ONE', signal(session_move_percent=1.8)),
        candidate('TWO', signal(session_move_percent=1.2)),
        candidate('THREE', signal(session_move_percent=0.8)),
    ]
    result = select_trade_candidates(
        candidates,
        CandidateSelectionConfig(top_n=2, min_score=0.0),
    )
    assert len(result.selected_candidates) == 2
    assert len(result.rejected_candidates) == 1
    assert result.rejected_candidates[0].reason == (
        'candidate_selection_outside_top_n'
    )


def test_candidate_selector_only_rejects_candidates_outside_top_n():
    candidates = [
        candidate(
            'BEST',
            signal(session_move_percent=2.0, trend_strength_percent=0.6),
        ),
        candidate(
            'SECOND',
            signal(session_move_percent=1.5, trend_strength_percent=0.4),
        ),
        candidate(
            'THIRD',
            signal(session_move_percent=1.0, trend_strength_percent=0.3),
        ),
        candidate(
            'FOURTH',
            signal(session_move_percent=0.5, trend_strength_percent=0.1),
        ),
    ]
    result = select_trade_candidates(
        candidates,
        CandidateSelectionConfig(top_n=2, min_score=0.0),
    )
    assert [item.symbol for item in result.selected_candidates] == [
        'BEST',
        'SECOND',
    ]
    assert {
        rejected.candidate.symbol: rejected.reason
        for rejected in result.rejected_candidates
    } == {
        'THIRD': 'candidate_selection_outside_top_n',
        'FOURTH': 'candidate_selection_outside_top_n',
    }


def test_candidate_selector_does_not_reject_high_spread_before_risk():
    high_spread = candidate(
        'WIDE',
        candidate_snapshot=snapshot(
            'WIDE',
            bid=98.0,
            ask=102.0,
            last=100.0,
        ),
    )
    result = select_trade_candidates(
        [high_spread],
        CandidateSelectionConfig(top_n=0, min_score=0.0),
    )
    assert result.selected_candidates == [high_spread]


def test_evaluated_selector_rejects_expected_profit_too_low():
    evaluated_candidate = EvaluatedTradeCandidate(
        candidate=TradeCandidate(
            symbol='LOW',
            snapshot=snapshot('LOW'),
            candle=candle('LOW'),
            signal=signal(),
            score=100.0,
            rank_reason='test',
            session_key=TEST_SESSION_KEY,
        ),
        economics=CandidateEconomics(
            position_value=100.0,
            expected_gross_profit=1.0,
            expected_net_profit=0.05,
            expected_net_profit_percent=0.05,
            estimated_total_cost=0.95,
            estimated_total_cost_percent=0.95,
            min_expected_net_profit_percent=0.10,
            required_min_expected_net_profit_amount=0.10,
        ),
    )
    result = select_evaluated_trade_candidates(
        [evaluated_candidate],
        CandidateSelectionConfig(top_n=0, min_score=0.0),
    )
    assert not result.selected_candidates
    assert result.rejected_candidates[0].reason == (
        'candidate_selection_expected_profit_too_low_after_fees'
    )


def test_evaluated_selector_prioritizes_tp_hard_reject_over_min_score():
    candidate_with_hard_rejection = TradeCandidate(
        symbol='LOW',
        snapshot=snapshot('LOW'),
        candle=candle('LOW'),
        signal=signal(),
        score=10.0,
        rank_reason='test',
        session_key=TEST_SESSION_KEY,
        tp_feasibility_hard_rejection_reason=(
            'candidate_selection_tp_feasibility_cost_to_tp_absurd'
        ),
    )
    result = select_evaluated_trade_candidates(
        [evaluated_candidate_with_profit(candidate_with_hard_rejection)],
        CandidateSelectionConfig(top_n=0, min_score=100.0),
    )
    assert not result.selected_candidates
    assert result.rejected_candidates[0].reason == (
        'candidate_selection_tp_feasibility_cost_to_tp_absurd'
    )


def test_negative_feasibility_contribution_is_rejected_only_by_visible_score():
    penalized_candidate = TradeCandidate(
        symbol='LOW',
        snapshot=snapshot('LOW'),
        candle=candle('LOW'),
        signal=signal(),
        score=95.0,
        rank_reason='test',
        session_key=TEST_SESSION_KEY,
        tp_feasibility_score=20.0,
        tp_feasibility_contribution=-9.0,
    )
    result = select_evaluated_trade_candidates(
        [evaluated_candidate_with_profit(penalized_candidate)],
        CandidateSelectionConfig(top_n=0, min_score=100.0),
    )
    assert not result.selected_candidates
    assert result.rejected_candidates[0].reason == (
        'candidate_selection_score_too_low'
    )


def test_exact_score_ranks_before_diagnostic_ev():
    base = candidate('BASE')
    lower_ev = evaluated_candidate_with_profit(
        replace(
            base,
            symbol='LOW_EV',
            score=102.0,
            net_expected_value_percent=-0.20,
        )
    )
    higher_ev = evaluated_candidate_with_profit(
        replace(
            base,
            symbol='HIGH_EV',
            score=101.0,
            net_expected_value_percent=0.10,
        )
    )

    ranked = rank_evaluated_trade_candidates([lower_ev, higher_ev])

    assert [item.candidate.symbol for item in ranked] == [
        'LOW_EV',
        'HIGH_EV',
    ]
