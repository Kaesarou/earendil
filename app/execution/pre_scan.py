from app.execution.candidate_selector import (
    CandidateSelectionConfig,
    CandidateSelectionResult,
    RejectedCandidateSelection,
    select_trade_candidates,
)

PreScanConfig = CandidateSelectionConfig
RejectedPreScanCandidate = RejectedCandidateSelection
PreScanResult = CandidateSelectionResult
pre_scan_candidates = select_trade_candidates
