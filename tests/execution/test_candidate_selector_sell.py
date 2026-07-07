from datetime import datetime, timezone

from app.execution.candidate_economics import CandidateEconomics, EvaluatedTradeCandidate
from app.execution.candidate_selector import CandidateSelectionConfig, select_evaluated_trade_candidates, select_trade_candidates
from app.execution.trade_candidate import TradeCandidate
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal

REASON = 'candidate_selection_sell_momentum_against_short'


def snapshot() -> MarketSnapshot:
    return MarketSnapshot(symbol='AMD', bid=99.9, ask=100.1, last=100.0, timestamp=datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc))


def candle() -> Candle:
    timestamp = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    return Candle(symbol='AMD', timeframe_seconds=60, open=99.0, high=101.0, low=98.5, close=100.0, volume=None, opened_at=timestamp, closed_at=timestamp)


def candidate(score: float = 150.0, sell_rejection_reason: str | None = REASON) -> TradeCandidate:
    return TradeCandidate(
        symbol='AMD',
        snapshot=snapshot(),
        candle=candle(),
        signal=Signal(action='SELL', confidence=0.8, reason='test'),
        score=score,
        rank_reason='test',
        sell_rejection_reason=sell_rejection_reason,
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


def test_trade_candidate_selector_rejects_strict_sell_before_min_score():
    result = select_trade_candidates(
        [candidate(score=10.0)],
        CandidateSelectionConfig(top_n=0, min_score=100.0),
    )

    assert not result.selected_candidates
    assert result.rejected_candidates[0].reason == REASON


def test_evaluated_candidate_selector_rejects_strict_sell_before_tp_feasibility_and_min_score():
    sell_candidate = TradeCandidate(
        **{
            **candidate(score=10.0).__dict__,
            'tp_feasibility_hard_rejection_reason': 'candidate_selection_tp_feasibility_cost_to_tp_absurd',
        }
    )

    result = select_evaluated_trade_candidates(
        [evaluated(sell_candidate)],
        CandidateSelectionConfig(top_n=0, min_score=100.0),
    )

    assert not result.selected_candidates
    assert result.rejected_candidates[0].reason == REASON
