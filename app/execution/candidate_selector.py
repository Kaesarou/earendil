import math
from dataclasses import dataclass

from app.execution.candidate_economics import EvaluatedTradeCandidate
from app.execution.candidate_ranking import rank_trade_candidates
from app.execution.trade_candidate import TradeCandidate


@dataclass(frozen=True)
class CandidateSelectionConfig:
    top_n: int
    min_score: float


@dataclass(frozen=True)
class RejectedCandidateSelection:
    candidate: TradeCandidate
    reason: str


@dataclass(frozen=True)
class RejectedEvaluatedCandidateSelection:
    evaluated_candidate: EvaluatedTradeCandidate
    reason: str


@dataclass(frozen=True)
class CandidateSelectionResult:
    selected_candidates: list[TradeCandidate]
    rejected_candidates: list[RejectedCandidateSelection]


@dataclass(frozen=True)
class EvaluatedCandidateSelectionResult:
    selected_candidates: list[EvaluatedTradeCandidate]
    rejected_candidates: list[RejectedEvaluatedCandidateSelection]


def select_trade_candidates(
    candidates: list[TradeCandidate],
    config: CandidateSelectionConfig,
) -> CandidateSelectionResult:
    selected_candidates: list[TradeCandidate] = []
    rejected_candidates: list[RejectedCandidateSelection] = []

    for candidate in rank_trade_candidates(candidates):
        if config.min_score > 0 and candidate.score < config.min_score:
            rejected_candidates.append(
                RejectedCandidateSelection(
                    candidate=candidate,
                    reason='candidate_selection_score_too_low',
                )
            )
            continue

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


def select_evaluated_trade_candidates(
    evaluated_candidates: list[EvaluatedTradeCandidate],
    config: CandidateSelectionConfig,
) -> EvaluatedCandidateSelectionResult:
    selected_candidates: list[EvaluatedTradeCandidate] = []
    rejected_candidates: list[RejectedEvaluatedCandidateSelection] = []

    for evaluated_candidate in rank_evaluated_trade_candidates(evaluated_candidates):
        candidate = evaluated_candidate.candidate
        economics = evaluated_candidate.economics

        if config.min_score > 0 and candidate.score < config.min_score:
            rejected_candidates.append(
                RejectedEvaluatedCandidateSelection(
                    evaluated_candidate=evaluated_candidate,
                    reason='candidate_selection_score_too_low',
                )
            )
            continue

        if (
            economics.expected_net_profit_percent
            < economics.min_expected_net_profit_percent
        ):
            rejected_candidates.append(
                RejectedEvaluatedCandidateSelection(
                    evaluated_candidate=evaluated_candidate,
                    reason='candidate_selection_expected_profit_too_low_after_fees',
                )
            )
            continue

        selected_candidates.append(evaluated_candidate)

    if config.top_n > 0 and len(selected_candidates) > config.top_n:
        kept_candidates = selected_candidates[: config.top_n]
        overflow_candidates = selected_candidates[config.top_n:]
        rejected_candidates.extend(
            RejectedEvaluatedCandidateSelection(
                evaluated_candidate=evaluated_candidate,
                reason='candidate_selection_outside_top_n',
            )
            for evaluated_candidate in overflow_candidates
        )
        selected_candidates = kept_candidates

    return EvaluatedCandidateSelectionResult(
        selected_candidates=selected_candidates,
        rejected_candidates=rejected_candidates,
    )


def rank_evaluated_trade_candidates(
    evaluated_candidates: list[EvaluatedTradeCandidate],
) -> list[EvaluatedTradeCandidate]:
    return sorted(
        evaluated_candidates,
        key=_evaluated_candidate_ranking_key,
        reverse=True,
    )


def _evaluated_candidate_ranking_key(
    evaluated_candidate: EvaluatedTradeCandidate,
) -> tuple[float, float, float]:
    score = evaluated_candidate.candidate.score
    score_bucket = math.floor(score / 5) * 5

    return (
        score_bucket,
        evaluated_candidate.economics.expected_net_profit,
        score,
    )
