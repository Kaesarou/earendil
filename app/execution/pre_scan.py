from dataclasses import dataclass

from app.execution.candidate_ranking import rank_trade_candidates
from app.execution.trade_candidate import TradeCandidate


@dataclass(frozen=True)
class PreScanConfig:
    top_n: int = 0


@dataclass(frozen=True)
class RejectedPreScanCandidate:
    candidate: TradeCandidate
    reason: str


@dataclass(frozen=True)
class PreScanResult:
    selected_candidates: list[TradeCandidate]
    rejected_candidates: list[RejectedPreScanCandidate]


def pre_scan_candidates(
    candidates: list[TradeCandidate],
    config: PreScanConfig,
) -> PreScanResult:

    selected_candidates: list[TradeCandidate] = []
    rejected_candidates: list[RejectedPreScanCandidate] = []

    for candidate in rank_trade_candidates(candidates):
        rejection_reason = _pre_scan_rejection_reason(candidate, config)

        if rejection_reason is not None:
            rejected_candidates.append(
                RejectedPreScanCandidate(
                    candidate=candidate,
                    reason=rejection_reason,
                )
            )
            continue

        selected_candidates.append(candidate)

    if config.top_n > 0 and len(selected_candidates) > config.top_n:
        kept_candidates = selected_candidates[: config.top_n]
        overflow_candidates = selected_candidates[config.top_n:]
        rejected_candidates.extend(
            RejectedPreScanCandidate(
                candidate=candidate,
                reason='pre_scan_outside_top_n',
            )
            for candidate in overflow_candidates
        )
        selected_candidates = kept_candidates

    return PreScanResult(
        selected_candidates=selected_candidates,
        rejected_candidates=rejected_candidates,
    )


def _pre_scan_rejection_reason(
    candidate: TradeCandidate,
    config: PreScanConfig,
) -> str | None:
    return None
