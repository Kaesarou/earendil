import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.journal.journal_policy import (
    decision_reason,
    decision_side,
    decision_symbol,
    is_hold_decision,
    is_rejected_decision,
    normalize_detail_level,
)
from app.journal.serialization import serialize_value


class DailySummaryAggregator:
    def __init__(self, *, run_id=None, strategy=None, profile=None, journal_detail_level='normal', started_at=None, max_items=10):
        self.run_id = run_id
        self.strategy = strategy
        self.profile = profile
        self.journal_detail_level = normalize_detail_level(journal_detail_level)
        self.started_at = started_at or datetime.now(timezone.utc)
        self.ended_at = None
        self.max_items = max_items
        self.event_counts = Counter()
        self.hold_reasons = Counter()
        self.rejection_reasons = Counter()
        self.error_types = Counter()
        self.candidates_by_symbol = Counter()
        self.orders_by_symbol = Counter()
        self.cooldowns_by_symbol = Counter()
        self.wait_confirmation_by_reason = Counter()
        self.entry_decisions_by_reason = Counter()
        self.market_data_rejections_by_reason = Counter()
        self.market_context_regimes = Counter()
        self.total_decisions = self.hold_total = self.candidate_total = 0
        self.selected_total = self.rejected_total = 0
        self.orders_submitted = self.orders_failed = self.orders_filled = 0
        self.positions_opened = self.positions_closed = self.positions_restored = 0
        self.force_closed = self.broker_failures = 0
        self.market_snapshots = self.candles_closed = 0
        self.market_data_received = self.market_data_accepted = 0
        self.market_data_quarantined = self.market_data_rejected = 0
        self.tradable_now_total = self.wait_confirmation_total = 0
        self.rejected_by_feasibility_total = self.orders_from_pending = 0
        self.enter_now_total = self.wait_for_retest_total = self.skip_total = 0
        self.pending_position_ids = set()
        self.gross_pnl_estimated = self.estimated_costs = self.net_pnl_estimated = 0.0
        self.pnl_from_pending = 0.0
        self.net_pnl_available = True
        self.top_rejected_candidates = []
        self.selected_candidates = []
        self.session_transitions = []
        self.errors = []

    def record(self, event_type: str, payload: dict[str, Any]) -> None:
        self.event_counts[event_type] += 1
        if event_type == 'market_snapshot_received':
            self.market_data_received += 1
        elif event_type == 'market_snapshot':
            self.market_snapshots += 1
            self.market_data_accepted += 1
        elif event_type == 'market_data_quarantined':
            self.market_data_quarantined += 1
            self._record_market_data_reason(payload)
        elif event_type == 'market_data_rejected':
            self.market_data_rejected += 1
            self._record_market_data_reason(payload)
        elif event_type == 'market_context_built':
            regime = _attribute(payload.get('market_context'), 'regime')
            value = _attribute(regime, 'value') or regime or 'unknown'
            self.market_context_regimes[str(value)] += 1
        elif event_type == 'candle_closed': self.candles_closed += 1
        elif event_type == 'candidate_detected': self._record_candidate_detected(payload)
        elif event_type == 'candidate_tp_feasibility': self._record_candidate_readiness(payload)
        elif event_type == 'candidate_selection': self._record_candidate_selection(payload)
        elif event_type == 'decision': self._record_decision(payload)
        elif event_type == 'cooldown_blocked': self._record_cooldown(payload)
        elif event_type == 'order_submitted':
            self.orders_submitted += 1
            self._increment_symbol_counter(self.orders_by_symbol, payload)
            if _is_pending_candidate(payload.get('candidate')): self.orders_from_pending += 1
        elif event_type == 'order_failed':
            self.orders_failed += 1
            self._increment_symbol_counter(self.orders_by_symbol, payload)
        elif event_type == 'order_filled':
            self.orders_filled += 1
            self._increment_symbol_counter(self.orders_by_symbol, payload)
        elif event_type == 'position_opened':
            self.positions_opened += 1
            if _is_pending_candidate(payload.get('candidate')):
                position_id = payload.get('position_id') or _attribute(payload.get('position'), 'position_id')
                if position_id: self.pending_position_ids.add(str(position_id))
        elif event_type == 'position_closed':
            self.positions_closed += 1
            self._record_closed_position_pnl(payload)
        elif event_type == 'position_restored': self.positions_restored += 1
        elif event_type in {'force_close_requested', 'force_close_completed', 'force_close'}: self.force_closed += 1
        elif event_type == 'session_state_changed': self._append_limited(self.session_transitions, self._session_transition_summary(payload))
        elif self._is_error_event(event_type): self._record_error(event_type, payload)

    def _record_market_data_reason(self, payload):
        validation = payload.get('validation')
        for reason in _as_list(_attribute(validation, 'reasons')):
            self.market_data_rejections_by_reason[str(reason)] += 1

    def _record_candidate_readiness(self, payload):
        for item in _as_list(payload.get('evaluated_candidates')):
            readiness = _attribute(item, 'readiness')
            value = _attribute(readiness, 'value') or readiness
            reason = _attribute(item, 'readiness_reason') or 'unknown_readiness'
            if value == 'tradable_now': self.tradable_now_total += 1
            elif value == 'wait_confirmation':
                self.wait_confirmation_total += 1
                self.wait_confirmation_by_reason[str(reason)] += 1
            elif value == 'reject': self.rejected_by_feasibility_total += 1

    def _record_entry_decision(self, item):
        candidate = _candidate_from_selection_item(item)
        evaluated = _attribute(item, 'evaluated_candidate') or item
        decision = _attribute(evaluated, 'entry_decision')
        if decision is None:
            return
        action = _attribute(decision, 'action')
        value = _attribute(action, 'value') or action
        reason = _attribute(decision, 'reason') or 'unknown_entry_decision'
        self.entry_decisions_by_reason[str(reason)] += 1
        if value == 'enter_now': self.enter_now_total += 1
        elif value == 'wait_for_retest': self.wait_for_retest_total += 1
        elif value == 'skip': self.skip_total += 1
        context = _attribute(candidate, 'market_context')
        regime = _attribute(context, 'regime')
        regime_value = _attribute(regime, 'value') or regime
        if regime_value is not None:
            self.market_context_regimes[str(regime_value)] += 1

    def finalize(self):
        self.ended_at = datetime.now(timezone.utc)
        return self.to_dict()

    def write(self, path):
        summary_path = Path(path)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(serialize_value(self.to_dict()), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def to_dict(self):
        return {
            'schema_version': 2, 'run_id': self.run_id, 'strategy': self.strategy,
            'profile': self.profile, 'journal_detail_level': self.journal_detail_level,
            'started_at': self.started_at, 'ended_at': self.ended_at,
            'events': {'by_type': dict(self.event_counts)},
            'market_data': {
                'snapshots': self.market_snapshots,
                'candles_closed': self.candles_closed,
                'received': self.market_data_received,
                'accepted': self.market_data_accepted,
                'quarantined': self.market_data_quarantined,
                'rejected': self.market_data_rejected,
                'rejections_by_reason': dict(self.market_data_rejections_by_reason),
            },
            'market_context': {'by_regime': dict(self.market_context_regimes)},
            'entry_decisions': {
                'enter_now': self.enter_now_total,
                'wait_for_retest': self.wait_for_retest_total,
                'skip': self.skip_total,
                'by_reason': dict(self.entry_decisions_by_reason),
            },
            'decisions': {
                'total': self.total_decisions, 'hold_total': self.hold_total,
                'candidate_total': self.candidate_total, 'selected_total': self.selected_total,
                'rejected_total': self.rejected_total, 'orders_submitted': self.orders_submitted,
                'orders_failed': self.orders_failed, 'orders_filled': self.orders_filled,
                'tradable_now_total': self.tradable_now_total,
                'wait_confirmation_total': self.wait_confirmation_total,
                'rejected_by_feasibility_total': self.rejected_by_feasibility_total,
                'wait_confirmation_by_reason': dict(self.wait_confirmation_by_reason),
            },
            'hold_reasons': dict(self.hold_reasons),
            'rejections': {'total': self.rejected_total, 'by_reason': dict(self.rejection_reasons), 'top_rejected_candidates': self.top_rejected_candidates},
            'selected_candidates': self.selected_candidates,
            'orders': {'submitted': self.orders_submitted, 'filled': self.orders_filled, 'failed': self.orders_failed, 'by_symbol': dict(self.orders_by_symbol), 'from_pending': self.orders_from_pending},
            'positions': {'opened': self.positions_opened, 'closed': self.positions_closed, 'restored': self.positions_restored, 'force_closed': self.force_closed},
            'pending_entries': {
                'registered': self.event_counts['pending_entry_registered'],
                'confirmed': self.event_counts['pending_entry_confirmed'],
                'expired': self.event_counts['pending_entry_expired'],
                'invalidated': self.event_counts['pending_entry_invalidated'],
                'updated': self.event_counts['pending_entry_updated'],
                'retest_detected': self.event_counts['pending_entry_retest_detected'],
            },
            'pnl': {
                'gross_estimated': round(self.gross_pnl_estimated, 4),
                'estimated_costs': round(self.estimated_costs, 4) if self.net_pnl_available else None,
                'net_estimated': round(self.net_pnl_estimated, 4) if self.net_pnl_available else None,
                'net_estimated_available': self.net_pnl_available,
                'from_pending': round(self.pnl_from_pending, 4),
            },
            'cooldown': {'blocked_total': sum(self.cooldowns_by_symbol.values()), 'by_symbol': dict(self.cooldowns_by_symbol)},
            'runtime': {'session_transitions': self.session_transitions},
            'errors': {'total': sum(self.error_types.values()), 'by_type': dict(self.error_types), 'samples': self.errors},
        }

    def _record_candidate_detected(self, payload):
        self.candidate_total += 1
        symbol = _attribute(payload.get('candidate'), 'symbol') or payload.get('symbol')
        if symbol: self.candidates_by_symbol[str(symbol)] += 1

    def _record_candidate_selection(self, payload):
        selected = _as_list(payload.get('selected_candidates'))
        rejected = _as_list(payload.get('rejected_candidates'))
        selected_source = _as_list(payload.get('selected_evaluated_candidates')) or selected
        rejected_source = _as_list(payload.get('rejected_evaluated_candidates')) or rejected
        self.selected_total += len(selected_source)
        self.rejected_total += len(rejected_source)
        for item in selected_source:
            self._record_entry_decision(item)
            self._append_limited(self.selected_candidates, self._selected_candidate_summary(item))
        for item in rejected_source:
            self._record_entry_decision(item)
            reason = _attribute(item, 'reason') or 'unknown_rejection'
            self.rejection_reasons[str(reason)] += 1
            self._remember_top_rejected_candidate(item, str(reason))

    def _record_decision(self, payload):
        self.total_decisions += 1
        reason = decision_reason(payload) or 'unknown_decision_reason'
        if is_hold_decision('decision', payload):
            self.hold_total += 1
            self.hold_reasons[reason] += 1
        elif is_rejected_decision('decision', payload):
            self.rejected_total += 1
            self.rejection_reasons[reason] += 1
            self._remember_top_rejected_decision(payload, reason)

    def _record_cooldown(self, payload):
        symbol = payload.get('symbol') or _attribute(payload.get('candidate'), 'symbol')
        if symbol: self.cooldowns_by_symbol[str(symbol)] += 1
        reason = payload.get('reason') or _attribute(payload.get('trade_plan'), 'reason') or 'cooldown_blocked'
        self.rejection_reasons[str(reason)] += 1

    def _record_closed_position_pnl(self, payload):
        closed = payload.get('closed_position')
        gross = _attribute(closed, 'gross_pnl')
        if gross is None: return
        gross = float(gross)
        self.gross_pnl_estimated += gross
        cost = _attribute(closed, 'estimated_total_cost')
        net = _attribute(closed, 'net_pnl_estimated')
        if cost is None or net is None:
            amount, pct = _attribute(closed, 'amount'), _attribute(closed, 'estimated_total_cost_percent')
            if amount is not None and pct is not None:
                cost = float(amount) * float(pct) / 100
                net = gross - cost
        if cost is None or net is None:
            self.net_pnl_available = False
            return
        self.estimated_costs += float(cost)
        self.net_pnl_estimated += float(net)
        position_id = _attribute(closed, 'position_id')
        if position_id is not None and str(position_id) in self.pending_position_ids:
            self.pnl_from_pending += float(net)
            self.pending_position_ids.discard(str(position_id))

    def _record_error(self, event_type, payload):
        self.error_types[event_type] += 1
        if event_type.startswith('broker_'): self.broker_failures += 1
        self._append_limited(self.errors, {'event_type': event_type, 'symbol': payload.get('symbol'), 'message': payload.get('message')})

    def _remember_top_rejected_decision(self, payload, reason):
        self._append_ranked(self.top_rejected_candidates, {'symbol': decision_symbol(payload), 'side': decision_side(payload), 'score': _candidate_score(payload.get('candidate')), 'reason': reason})

    def _remember_top_rejected_candidate(self, item, reason):
        summary = _candidate_summary(_candidate_from_selection_item(item)); summary['reason'] = reason
        self._append_ranked(self.top_rejected_candidates, summary)

    def _selected_candidate_summary(self, item): return _candidate_summary(_candidate_from_selection_item(item))
    def _session_transition_summary(self, payload): return {'symbol': payload.get('symbol'), 'from': payload.get('previous_state'), 'to': payload.get('new_state'), 'reason': payload.get('reason'), 'session_key': payload.get('session_key')}
    def _increment_symbol_counter(self, counter, payload):
        if payload.get('symbol'): counter[str(payload['symbol'])] += 1
    def _append_limited(self, items, item):
        if len(items) < self.max_items: items.append(item)
    def _append_ranked(self, items, item):
        items.append(item); items.sort(key=lambda value: value.get('score') or 0.0, reverse=True); del items[self.max_items:]
    def _is_error_event(self, event_type): return event_type == 'error' or event_type.endswith('_error') or event_type.endswith('_warning') or event_type.startswith('broker_')


def _is_pending_candidate(candidate):
    metadata = _attribute(_attribute(candidate, 'signal'), 'metadata') or {}
    return _attribute(metadata, 'entry_origin') == 'pending_confirmation'


def _candidate_from_selection_item(item):
    direct = _attribute(item, 'candidate')
    if direct is not None: return direct
    evaluated = _attribute(item, 'evaluated_candidate')
    if evaluated is not None: return _attribute(evaluated, 'candidate')
    direct_evaluated = _attribute(item, 'candidate')
    return direct_evaluated or item


def _candidate_summary(candidate):
    signal = _attribute(candidate, 'signal')
    return {'candidate_id': _attribute(candidate, 'candidate_id'), 'symbol': _attribute(candidate, 'symbol'), 'side': _attribute(signal, 'action'), 'score': _candidate_score(candidate), 'reason': _attribute(candidate, 'rank_reason')}


def _candidate_score(candidate):
    score = _attribute(candidate, 'score'); return None if score is None else float(score)


def _attribute(value, name):
    if value is None: return None
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def _as_list(value):
    if value is None: return []
    if isinstance(value, (list, tuple)): return list(value)
    return list(value)
