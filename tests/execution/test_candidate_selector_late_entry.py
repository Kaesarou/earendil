from datetime import datetime, timezone

from app.execution.candidate_economics import CandidateEconomics, EvaluatedTradeCandidate
from app.execution.candidate_selector import CandidateSelectionConfig, select_evaluated_trade_candidates, select_trade_candidates
from app.execution.trade_candidate import TradeCandidate
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal

LATE_FIELD = 'late_' + 'entry_rejection_reason'
REASON = 'candidate_selection_' + 'late_' + 'entry_exhausted_decelerating'
TP_FIELD = 'tp_feasibility_' + 'hard_rejection_reason'
TP_REASON = 'candidate_selection_tp_feasibility_' + 'cost_to_tp_absurd'


def snapshot(symbol: str = 'AMD') -> MarketSnapshot:
    return MarketSnapshot(symbol=symbol, bid=99.9, ask=100.1, last=100.0, timestamp=datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc))


def candle(symbol: str = 'AMD') -> Candle:
    timestamp = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    return Candle(symbol=symbol, timeframe_seconds=60, open=99.0, high=101.0, low=98.5, close=100.0, volume=None, opened_at=timestamp, closed_at=timestamp)


def candidate(score: float = 10.0, rejection_reason: str | None = REASON) -> TradeCandidate:
    return TradeCandidate(
        symbol='AMD',
        snapshot=snapshot(),
        candle=candle(),
        signal=Signal(action='BUY', setup_quality=0.8, reason='test'),
        score=score,
        rank_reason='test',
        **{LATE_FIELD: rejection_reason},
    )


def evaluated(candidate: TradeCandidate) -> EvaluatedTradeCandidate:
    return EvaluatedTradeCandidate(
        candidate=candidate,
        economics=CandidateEconomics(
            position_value=100.0,
            expected_gross_profit=2.0,
            expected_net_profit=1.0,
            expected_net_profit_percent=1.0,
            estimated_total_cost=1.0,
            estimated_total_cost_percent=1.0,
            min_expected_net_profit_percent=0.1,
            required_min_expected_net_profit_amount=0.1,
        ),
    )


def test_trade_candidate_selector_rejects_strict_entry_timing_before_min_score():
    result = select_trade_candidates(
        [candidate(score=10.0)],
        CandidateSelectionConfig(top_n=0, min_score=100.0),
    )

    assert not result.selected_candidates
    assert result.rejected_candidates[0].reason == REASON


def test_evaluated_candidate_selector_rejects_strict_entry_timing_first():
    blocked_candidate = TradeCandidate(
        **{
            **candidate(score=10.0).__dict__,
            TP_FIELD: TP_REASON,
        }
    )

    result = select_evaluated_trade_candidates(
        [evaluated(blocked_candidate)],
        CandidateSelectionConfig(top_n=0, min_score=100.0),
    )

    assert not result.selected_candidates
    assert result.rejected_candidates[0].reason == REASON
