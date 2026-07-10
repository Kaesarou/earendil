import math
from dataclasses import dataclass

from app.execution.candidate_economics import EvaluatedTradeCandidate
from app.execution.candidate_ranking import rank_trade_candidates
from app.execution.candidate_readiness import CandidateReadiness
from app.execution.trade_candidate import TradeCandidate


@dataclass(frozen=True)
class CandidateSelectionConfig:
    top_n: int
    min_score: float
    dynamic_min_score: float | None = None


@dataclass(frozen=True)
class RejectedCandidateSelection:
    candidate: TradeCandidate
    reason: str


@dataclass(frozen=True)
class RejectedEvaluatedCandidateSelection:
    evaluated_candidate: EvaluatedTradeCandidate
    reason: str
    min_score_used: float | None = None
    selection_threshold_source: str | None = None


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
        if candidate.late_entry_rejection_reason is not None:
            rejected_candidates.append(
                RejectedCandidateSelection(
                    candidate=candidate,
                    reason=candidate.late_entry_rejection_reason,
                )
            )
            continue
        if candidate.sell_rejection_reason is not None:
            rejected_candidates.append(
                RejectedCandidateSelection(
                    candidate=candidate,
                    reason=candidate.sell_rejection_reason,
                )
            )
            continue
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
        overflow_candidates = selected_candidates[config.top_n :]
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
        min_score_used, threshold_source = selection_threshold_for(
            evaluated_candidate,
            config,
        )
        if evaluated_candidate.readiness == CandidateReadiness.WAIT_CONFIRMATION:
            rejected_candidates.append(
                RejectedEvaluatedCandidateSelection(
                    evaluated_candidate=evaluated_candidate,
                    reason=evaluated_candidate.readiness_reason or 'candidate_wait_confirmation',
                    min_score_used=min_score_used,
                    selection_threshold_source=threshold_source,
                )
            )
            continue
        if evaluated_candidate.readiness == CandidateReadiness.REJECT:
            rejected_candidates.append(
                RejectedEvaluatedCandidateSelection(
                    evaluated_candidate=evaluated_candidate,
                    reason=evaluated_candidate.readiness_reason or 'candidate_readiness_reject',
                    min_score_used=min_score_used,
                    selection_threshold_source=threshold_source,
                )
            )
            continue
        if candidate.late_entry_rejection_reason is not None:
            rejected_candidates.append(
                RejectedEvaluatedCandidateSelection(
                    evaluated_candidate=evaluated_candidate,
                    reason=candidate.late_entry_rejection_reason,
                    min_score_used=min_score_used,
                    selection_threshold_source=threshold_source,
                )
            )
            continue
        if candidate.sell_rejection_reason is not None:
            rejected_candidates.append(
                RejectedEvaluatedCandidateSelection(
                    evaluated_candidate=evaluated_candidate,
                    reason=candidate.sell_rejection_reason,
                    min_score_used=min_score_used,
                    selection_threshold_source=threshold_source,
                )
            )
            continue
        if candidate.tp_feasibility_hard_rejection_reason is not None:
            rejected_candidates.append(
                RejectedEvaluatedCandidateSelection(
                    evaluated_candidate=evaluated_candidate,
                    reason=candidate.tp_feasibility_hard_rejection_reason,
                    min_score_used=min_score_used,
                    selection_threshold_source=threshold_source,
                )
            )
            continue
        if min_score_used > 0 and candidate.score < min_score_used:
            rejected_candidates.append(
                RejectedEvaluatedCandidateSelection(
                    evaluated_candidate=evaluated_candidate,
                    reason='candidate_selection_score_too_low',
                    min_score_used=min_score_used,
                    selection_threshold_source=threshold_source,
                )
            )
            continue
        if economics.expected_net_profit_percent < economics.min_expected_net_profit_percent:
            rejected_candidates.append(
                RejectedEvaluatedCandidateSelection(
                    evaluated_candidate=evaluated_candidate,
                    reason='candidate_selection_expected_profit_too_low_after_fees',
                    min_score_used=min_score_used,
                    selection_threshold_source=threshold_source,
                )
            )
            continue
        selected_candidates.append(evaluated_candidate)
    if config.top_n > 0 and len(selected_candidates) > config.top_n:
        kept_candidates = selected_candidates[: config.top_n]
        overflow_candidates = selected_candidates[config.top_n :]
        rejected_candidates.extend(
            RejectedEvaluatedCandidateSelection(
                evaluated_candidate=evaluated_candidate,
                reason='candidate_selection_outside_top_n',
                min_score_used=selection_threshold_for(evaluated_candidate, config)[0],
                selection_threshold_source=selection_threshold_for(
                    evaluated_candidate,
                    config,
                )[1],
            )
            for evaluated_candidate in overflow_candidates
        )
        selected_candidates = kept_candidates
    return EvaluatedCandidateSelectionResult(
        selected_candidates=selected_candidates,
        rejected_candidates=rejected_candidates,
    )


def selection_threshold_for(
    evaluated_candidate: EvaluatedTradeCandidate,
    config: CandidateSelectionConfig,
) -> tuple[float, str]:
    effective_sl_tp = evaluated_candidate.effective_sl_tp
    if effective_sl_tp is not None:
        selection_min_score = effective_sl_tp.metadata.get('selection_min_score')
        if selection_min_score is not None:
            return float(selection_min_score), 'effective_sl_tp_selection_min_score'
        if effective_sl_tp.mode == 'dynamic' and config.dynamic_min_score is not None:
            return config.dynamic_min_score, 'dynamic_min_score'
    return config.min_score, 'min_score'


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
    return (score_bucket, evaluated_candidate.economics.expected_net_profit, score)
