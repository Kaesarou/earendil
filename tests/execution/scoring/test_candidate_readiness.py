from app.execution.candidate_readiness import (
    CandidateReadiness,
    evaluate_candidate_readiness,
)


def classify(runway, penalty, hard=None):
    return evaluate_candidate_readiness(
        runway_score=runway,
        feasibility_penalty=penalty,
        hard_rejection_reason=hard,
        min_runway_score=25.0,
        severe_penalty=40.0,
    )


def test_tradable_now_when_runway_and_penalty_are_acceptable():
    decision = classify(25.0, 39.999999)

    assert decision.readiness == CandidateReadiness.TRADABLE_NOW


def test_amat_boundary_uses_raw_runway_value():
    decision = classify(20.049999, 39.98)

    assert decision.readiness == CandidateReadiness.WAIT_CONFIRMATION
    assert decision.reason == 'insufficient_runway'


def test_severe_penalty_waits_even_with_large_runway():
    decision = classify(80.0, 40.0)

    assert decision.readiness == CandidateReadiness.WAIT_CONFIRMATION
    assert decision.reason == 'severe_feasibility_penalty'


def test_hard_rejection_is_reject():
    decision = classify(100.0, 0.0, 'spread_prohibitive')

    assert decision.readiness == CandidateReadiness.REJECT
    assert decision.reason == 'spread_prohibitive'
