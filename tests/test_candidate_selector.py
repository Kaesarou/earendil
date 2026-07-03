from datetime import datetime, timezone

from app.execution.candidate_ranking import build_trade_candidate
from app.execution.candidate_selector import CandidateSelectionConfig, select_trade_candidates
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