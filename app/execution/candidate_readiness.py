from dataclasses import dataclass
from enum import StrEnum


class CandidateReadiness(StrEnum):
    TRADABLE_NOW = 'tradable_now'
    WAIT_CONFIRMATION = 'wait_confirmation'
    REJECT = 'reject'


@dataclass(frozen=True)
class CandidateReadinessDecision:
    readiness: CandidateReadiness
    reason: str


def evaluate_candidate_readiness(
    *,
    runway_score: float,
    feasibility_penalty: float,
    hard_rejection_reason: str | None,
    min_runway_score: float,
    severe_penalty: float,
) -> CandidateReadinessDecision:
    """Compatibility diagnostic only.

    Entry timing is decided by EntryDecisionEngine. Feasibility may still hard-reject
    a candidate, but a severe penalty no longer registers a pending entry by itself.
    """
    if hard_rejection_reason is not None:
        return CandidateReadinessDecision(
            readiness=CandidateReadiness.REJECT,
            reason=hard_rejection_reason,
        )
    return CandidateReadinessDecision(
        readiness=CandidateReadiness.TRADABLE_NOW,
        reason='entry_decision_required',
    )
