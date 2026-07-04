from datetime import datetime, timezone

from app.execution.candidate_economics import CandidateEconomics, EvaluatedTradeCandidate
from app.execution.candidate_ranking import build_trade_candidate
from app.execution.candidate_selector import (
    CandidateSelectionConfig,
    select_evaluated_trade_candidates,
    select_trade_candidates,
)
from app.execution.trade_candidate import TradeCandidate
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal


def snapshot(symbol: str, bid: float = 99.9, ask: float = 100.1, last: float = 100.0) -> MarketSnapshot:
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
        confidence=0.8,
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
    assert result.rejected_candidates[0].reason == 'candidate_selection_outside_top_n'


def test_candidate_selector_only_rejects_candidates_outside_top_n():
    candidates = [
        candidate('BEST', signal(session_move_percent=2.0, trend_strength_percent=0.6)),
        candidate('SECOND', signal(session_move_percent=1.5, trend_strength_percent=0.4)),
        candidate('THIRD', signal(session_move_percent=1.0, trend_strength_percent=0.3)),
        candidate('FOURTH', signal(session_move_percent=0.5, trend_strength_percent=0.1)),
    ]

    result = select_trade_candidates(
        candidates,
        CandidateSelectionConfig(top_n=2, min_score=0.0),
    )

    assert len(result.selected_candidates) == 2
    assert len(result.rejected_candidates) == 2

    assert [candidate.symbol for candidate in result.selected_candidates] == [
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

    assert {
        rejected.reason
        for rejected in result.rejected_candidates
    } == {'candidate_selection_outside_top_n'}


def test_candidate_selector_does_not_reject_high_spread_candidate_before_risk_manager():
    high_spread = candidate(
        'WIDE',
        candidate_snapshot=snapshot('WIDE', bid=98.0, ask=102.0, last=100.0),
    )

    result = select_trade_candidates(
        [high_spread],
        CandidateSelectionConfig(top_n=0, min_score=0.0),
    )

    assert result.selected_candidates == [high_spread]
    assert result.rejected_candidates == []


def test_rejects_candidate_below_min_score():
    low_score_candidate = make_candidate(score=114.99)

    result = select_trade_candidates(
        [low_score_candidate],
        CandidateSelectionConfig(top_n=0, min_score=115.0),
    )

    assert result.selected_candidates == []
    assert len(result.rejected_candidates) == 1
    assert result.rejected_candidates[0].reason == 'candidate_selection_score_too_low'


def test_keeps_candidate_at_min_score():
    candidate = make_candidate(score=115.0)

    result = select_trade_candidates(
        [candidate],
        CandidateSelectionConfig(top_n=0, min_score=115.0),
    )

    assert result.selected_candidates == [candidate]
    assert result.rejected_candidates == []


def test_applies_top_n_after_min_score_filter():
    candidate_130 = make_candidate(score=130)
    candidate_120 = make_candidate(score=120)
    candidate_110 = make_candidate(score=110)

    result = select_trade_candidates(
        [candidate_110, candidate_130, candidate_120],
        CandidateSelectionConfig(top_n=1, min_score=115.0),
    )

    assert result.selected_candidates == [candidate_130]

    rejected_reasons = [rejected.reason for rejected in result.rejected_candidates]
    assert 'candidate_selection_score_too_low' in rejected_reasons
    assert 'candidate_selection_outside_top_n' in rejected_reasons


def test_evaluated_candidate_selector_rejects_candidate_below_min_score():
    low_score_candidate = make_evaluated_candidate(score=114.99)

    result = select_evaluated_trade_candidates(
        [low_score_candidate],
        CandidateSelectionConfig(top_n=0, min_score=115.0),
    )

    assert result.selected_candidates == []
    assert len(result.rejected_candidates) == 1
    assert result.rejected_candidates[0].reason == 'candidate_selection_score_too_low'


def test_evaluated_candidate_selector_rejects_candidate_below_min_expected_net_profit_percent():
    low_profit_candidate = make_evaluated_candidate(
        expected_net_profit_percent=0.05,
        min_expected_net_profit_percent=0.10,
    )

    result = select_evaluated_trade_candidates(
        [low_profit_candidate],
        CandidateSelectionConfig(top_n=0, min_score=0.0),
    )

    assert result.selected_candidates == []
    assert len(result.rejected_candidates) == 1
    assert result.rejected_candidates[0].reason == (
        'candidate_selection_expected_profit_too_low_after_fees'
    )


def test_evaluated_candidate_selector_keeps_candidate_at_min_expected_net_profit_percent():
    candidate = make_evaluated_candidate(
        expected_net_profit_percent=0.10,
        min_expected_net_profit_percent=0.10,
    )

    result = select_evaluated_trade_candidates(
        [candidate],
        CandidateSelectionConfig(top_n=0, min_score=0.0),
    )

    assert result.selected_candidates == [candidate]
    assert result.rejected_candidates == []


def test_evaluated_candidate_selector_ranks_by_score_bucket_then_expected_net_profit():
    score_124_net_4 = make_evaluated_candidate(symbol='A', score=124, expected_net_profit=4)
    score_122_net_12 = make_evaluated_candidate(symbol='B', score=122, expected_net_profit=12)
    score_136_net_6 = make_evaluated_candidate(symbol='C', score=136, expected_net_profit=6)

    result = select_evaluated_trade_candidates(
        [score_124_net_4, score_122_net_12, score_136_net_6],
        CandidateSelectionConfig(top_n=0, min_score=0.0),
    )

    assert [item.candidate.symbol for item in result.selected_candidates] == [
        'C',
        'B',
        'A',
    ]


def test_evaluated_candidate_selector_applies_top_n_after_economic_filter():
    strong = make_evaluated_candidate(symbol='STRONG', score=130, expected_net_profit=5)
    weak_profit = make_evaluated_candidate(
        symbol='WEAK',
        score=129,
        expected_net_profit=20,
        expected_net_profit_percent=0.05,
        min_expected_net_profit_percent=0.10,
    )
    second = make_evaluated_candidate(symbol='SECOND', score=128, expected_net_profit=4)

    result = select_evaluated_trade_candidates(
        [second, weak_profit, strong],
        CandidateSelectionConfig(top_n=1, min_score=0.0),
    )

    assert result.selected_candidates == [strong]
    rejected_reasons = [rejected.reason for rejected in result.rejected_candidates]
    assert 'candidate_selection_expected_profit_too_low_after_fees' in rejected_reasons
    assert 'candidate_selection_outside_top_n' in rejected_reasons


def make_candidate(
    *,
    symbol: str = "AAPL",
    action: str = "BUY",
    score: float = 120.0,
    confidence: float = 0.8,
    reason: str = "test_signal",
) -> TradeCandidate:
    now = datetime.now(timezone.utc)

    snapshot = MarketSnapshot(
        symbol=symbol,
        bid=99.95,
        ask=100.05,
        last=100.0,
        timestamp=now,
    )

    candle = Candle(
        symbol=symbol,
        timeframe_seconds=60,
        open=99.5,
        high=100.2,
        low=99.4,
        close=100.0,
        volume=None,
        opened_at=now,
        closed_at=now,
    )

    signal = Signal(
        action=action,
        confidence=confidence,
        reason=reason,
        metadata={
            "session_move_percent": 1.0,
            "trend_strength_percent": 0.2,
            "breakout_percent": 0.1 if action == "BUY" else 0.0,
            "breakdown_percent": 0.1 if action == "SELL" else 0.0,
            "candle_range_percent": 0.8,
            "close_position_percent": 85.0 if action == "BUY" else 15.0,
        },
    )

    return TradeCandidate(
        symbol=symbol,
        snapshot=snapshot,
        candle=candle,
        signal=signal,
        score=score,
        rank_reason=f"test_score={score}",
    )


def make_evaluated_candidate(
    *,
    symbol: str = 'AAPL',
    score: float = 120.0,
    expected_net_profit: float = 1.0,
    expected_net_profit_percent: float = 0.5,
    min_expected_net_profit_percent: float = 0.1,
) -> EvaluatedTradeCandidate:
    return EvaluatedTradeCandidate(
        candidate=make_candidate(symbol=symbol, score=score),
        economics=CandidateEconomics(
            position_value=100.0,
            expected_gross_profit=2.0,
            expected_net_profit=expected_net_profit,
            expected_net_profit_percent=expected_net_profit_percent,
            estimated_total_cost=1.0,
            estimated_total_cost_percent=1.0,
            min_expected_net_profit_percent=min_expected_net_profit_percent,
            required_min_expected_net_profit_amount=0.1,
        ),
    )
