from dataclasses import dataclass

from app.execution.candidate_ranking import rank_trade_candidates
from app.execution.trade_candidate import TradeCandidate


@dataclass(frozen=True)
class CandidateSelectionConfig:
    top_n: int = 0


@dataclass(frozen=True)
class RejectedCandidateSelection:
    candidate: TradeCandidate
    reason: str


@dataclass(frozen=True)
class CandidateSelectionResult:
    selected_candidates: list[TradeCandidate]
    rejected_candidates: list[RejectedCandidateSelection]


def select_trade_candidates(
    candidates: list[TradeCandidate],
    config: CandidateSelectionConfig,
) -> CandidateSelectionResult:
    selected_candidates: list[TradeCandidate] = []
    rejected_candidates: list[RejectedCandidateSelection] = []

    for candidate in rank_trade_candidates(candidates):
        selected_candidates.append(candidate)

    if config.top_n > 0 and len(selected_candidates) > config.top_n:
        kept_candidates = selected_candidates[: config.top_n]
        overflow_candidates = selected_candidates[config.top_n:]
        rejected_candidates.extend(
            RejectedCandidateSelection(
                candidate=candidate,
                reason='candidate_selection_outside_top_n',
            )
            for candidate in overflow_candidates
        )
        selected_candidates = kept_candidates

    return CandidateSelectionResult(
        selected_candidates=selected_candidates,
        rejected_candidates=rejected_candidates,
    )
