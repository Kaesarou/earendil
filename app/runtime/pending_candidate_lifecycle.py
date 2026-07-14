from dataclasses import replace

from app.execution.candidate_economics import EvaluatedTradeCandidate
from app.execution.candidate_selector import RejectedEvaluatedCandidateSelection
from app.execution.entry_decision import EntryAction
from app.execution.trade_candidate import TradeCandidate
from app.journal.jsonl_journal import JsonlJournal
from app.runtime.pending_entry import PendingEntryEvent, PendingEntryManager, PendingEntryState
from app.runtime.pending_entry_flow import write_pending_events

_RETRYABLE_SELECTION_REASONS = {
    'candidate_selection_outside_top_n',
    'candidate_selection_score_too_low',
}


def pending_entry_key(candidate: TradeCandidate) -> str | None:
    raw_key = (candidate.signal.metadata or {}).get('pending_entry_id')
    return str(raw_key) if raw_key else None


def economics_rejection_reason(
    evaluated_candidate: EvaluatedTradeCandidate,
) -> str | None:
    economics = evaluated_candidate.economics
    if economics.expected_net_profit_percent < economics.min_expected_net_profit_percent:
        return 'candidate_selection_expected_profit_too_low_after_fees'
    return None


def invalidate_pending_candidate(
    *,
    candidate: TradeCandidate,
    reason: str,
    pending_entry_manager: PendingEntryManager | None,
    trade_journal: JsonlJournal,
) -> None:
    if pending_entry_manager is None:
        return
    pending_key = pending_entry_key(candidate)
    if pending_key is None:
        return
    removed = pending_entry_manager.remove(pending_key)
    if removed is None:
        return
    invalidated = replace(removed, state=PendingEntryState.INVALIDATED)
    write_pending_events(
        trade_journal,
        (PendingEntryEvent('pending_entry_invalidated', invalidated, reason),),
    )


def keep_pending_waiting(
    *,
    candidate: TradeCandidate,
    reason: str,
    pending_entry_manager: PendingEntryManager | None,
    trade_journal: JsonlJournal,
) -> None:
    if pending_entry_manager is None:
        return
    pending_key = pending_entry_key(candidate)
    if pending_key is None:
        return
    pending_entry_manager.mark_waiting_after_recalculation(pending_key)
    pending = pending_entry_manager.get(pending_key)
    if pending is None:
        return
    write_pending_events(
        trade_journal,
        (PendingEntryEvent('pending_entry_updated', pending, reason),),
    )


def reconcile_pending_selection_rejections(
    *,
    rejected_candidates: list[RejectedEvaluatedCandidateSelection],
    pending_entry_manager: PendingEntryManager | None,
    trade_journal: JsonlJournal,
) -> None:
    for rejected in rejected_candidates:
        evaluated_candidate = rejected.evaluated_candidate
        candidate = evaluated_candidate.candidate
        decision = evaluated_candidate.entry_decision
        if (
            pending_entry_manager is not None
            and decision is not None
            and decision.action == EntryAction.WAIT_FOR_RETEST
        ):
            existing_key = pending_entry_key(candidate)
            if existing_key is not None:
                keep_pending_waiting(
                    candidate=candidate,
                    reason=f'entry_decision:{decision.reason}',
                    pending_entry_manager=pending_entry_manager,
                    trade_journal=trade_journal,
                )
            else:
                write_pending_events(
                    trade_journal,
                    pending_entry_manager.register(
                        evaluated_candidate=evaluated_candidate,
                        max_candles=5,
                    ),
                )
            continue
        if rejected.reason in _RETRYABLE_SELECTION_REASONS:
            keep_pending_waiting(
                candidate=candidate,
                reason=f'selection_retry:{rejected.reason}',
                pending_entry_manager=pending_entry_manager,
                trade_journal=trade_journal,
            )
            continue
        invalidate_pending_candidate(
            candidate=candidate,
            reason=f'selection_reject:{rejected.reason}',
            pending_entry_manager=pending_entry_manager,
            trade_journal=trade_journal,
        )
