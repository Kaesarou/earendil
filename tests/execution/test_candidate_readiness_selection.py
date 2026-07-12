from dataclasses import replace

from app.execution.candidate_economics import EvaluatedTradeCandidate
from app.execution.candidate_readiness import CandidateReadiness
from app.execution.candidate_selector import (
    CandidateSelectionConfig,
    select_evaluated_trade_candidates,
)
from tests.execution.test_candidate_selector import candidate, evaluated_candidate_with_profit


def evaluated(symbol: str, score: float, readiness: CandidateReadiness):
    base = evaluated_candidate_with_profit(candidate(symbol))
    return replace(
        base,
        candidate=replace(base.candidate, score=score),
        readiness=readiness,
        readiness_reason=(
            'insufficient_runway'
            if readiness == CandidateReadiness.WAIT_CONFIRMATION
            else 'tp_feasibility_ready'
        ),
    )


def test_huge_wait_score_never_participates_in_top_n():
    waiting = evaluated('WAIT', 999.0, CandidateReadiness.WAIT_CONFIRMATION)
    tradable = evaluated('NOW', 120.0, CandidateReadiness.TRADABLE_NOW)

    result = select_evaluated_trade_candidates(
        [waiting, tradable],
        CandidateSelectionConfig(top_n=1, min_score=100.0),
    )

    assert [item.candidate.symbol for item in result.selected_candidates] == ['NOW']
    assert len(result.rejected_candidates) == 1
    assert result.rejected_candidates[0].evaluated_candidate.candidate.symbol == 'WAIT'
    assert result.rejected_candidates[0].reason == 'insufficient_runway'


def test_rejected_readiness_is_never_selected():
    rejected = evaluated('REJECT', 999.0, CandidateReadiness.REJECT)
    rejected = replace(rejected, readiness_reason='invalid_trade_structure')

    result = select_evaluated_trade_candidates(
        [rejected],
        CandidateSelectionConfig(top_n=1, min_score=0.0),
    )

    assert not result.selected_candidates
    assert result.rejected_candidates[0].reason == 'invalid_trade_structure'
