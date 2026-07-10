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
    if hard_rejection_reason is not None:
        return CandidateReadinessDecision(
            readiness=CandidateReadiness.REJECT,
            reason=hard_rejection_reason,
        )
    if feasibility_penalty >= severe_penalty:
        return CandidateReadinessDecision(
            readiness=CandidateReadiness.WAIT_CONFIRMATION,
            reason='severe_feasibility_penalty',
        )
    if runway_score < min_runway_score:
        return CandidateReadinessDecision(
            readiness=CandidateReadiness.WAIT_CONFIRMATION,
            reason='insufficient_runway',
        )
    return CandidateReadinessDecision(
        readiness=CandidateReadiness.TRADABLE_NOW,
        reason='tp_feasibility_ready',
    )
