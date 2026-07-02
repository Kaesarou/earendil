from dataclasses import dataclass

from app.execution.candidate_selector import (
    CandidateSelectionConfig,
    CandidateSelectionResult,
    select_trade_candidates,
)
from app.execution.trade_candidate import TradeCandidate

PreScanConfig = CandidateSelectionConfig
PreScanResult = CandidateSelectionResult
pre_scan_candidates = select_trade_candidates


@dataclass(frozen=True)
class RejectedPreScanCandidate:
    candidate: TradeCandidate
    reason: str

    def __post_init__(self) -> None:
        if self.reason == 'pre_scan_outside_top_n':
            object.__setattr__(self, 'reason', 'candidate_selection_outside_top_n')
