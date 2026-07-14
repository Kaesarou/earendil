from dataclasses import dataclass
from enum import StrEnum


class CandidateReadiness(StrEnum):
    TRADABLE_NOW = 'tradable_now'
    REJECT = 'reject'


@dataclass(frozen=True)
class CandidateReadinessDecision:
    readiness: CandidateReadiness
    reason: str


def evaluate_candidate_readiness(*, hard_rejection_reason: str | None) -> CandidateReadinessDecision:
    if hard_rejection_reason is not None:
        return CandidateReadinessDecision(
            readiness=CandidateReadiness.REJECT,
            reason=hard_rejection_reason,
        )
    return CandidateReadinessDecision(
        readiness=CandidateReadiness.TRADABLE_NOW,
        reason='entry_decision_required',
    )
