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


def test_readiness_no_longer_routes_low_runway_to_pending():
    decision = classify(5.0, 39.0)

    assert decision.readiness == CandidateReadiness.TRADABLE_NOW
    assert decision.reason == 'entry_decision_required'


def test_readiness_no_longer_routes_severe_penalty_to_pending():
    decision = classify(80.0, 40.0)

    assert decision.readiness == CandidateReadiness.TRADABLE_NOW
    assert decision.reason == 'entry_decision_required'


def test_hard_rejection_is_still_reject():
    decision = classify(100.0, 0.0, 'spread_prohibitive')

    assert decision.readiness == CandidateReadiness.REJECT
    assert decision.reason == 'spread_prohibitive'
