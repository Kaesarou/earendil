from app.execution.candidate_readiness import (
    CandidateReadiness,
    evaluate_candidate_readiness,
)


def test_probabilistic_conditions_do_not_exist_in_readiness_layer():
    decision = evaluate_candidate_readiness(
        hard_rejection_reason=None,
    )

    assert decision.readiness == CandidateReadiness.TRADABLE_NOW
    assert decision.reason == 'entry_decision_required'


def test_hard_rejection_is_still_reject():
    decision = evaluate_candidate_readiness(
        hard_rejection_reason='invalid_trade_structure',
    )

    assert decision.readiness == CandidateReadiness.REJECT
    assert decision.reason == 'invalid_trade_structure'
