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
    def __init__(
        self,
        *,
        run_id: str | None = None,
        strategy: str | None = None,
        profile: str | None = None,
        journal_detail_level: str = 'normal',
        started_at: datetime | None = None,
        max_items: int = 10,
    ):
        self.run_id = run_id
        self.strategy = strategy
        self.profile = profile
        self.journal_detail_level = normalize_detail_level(journal_detail_level)
        self.started_at = started_at or datetime.now(timezone.utc)
        self.ended_at: datetime | None = None
        self.max_items = max_items

        self.event_counts: Counter[str] = Counter()
        self.hold_reasons: Counter[str] = Counter()
        self.rejection_reasons: Counter[str] = Counter()
        self.error_types: Counter[str] = Counter()
        self.candidates_by_symbol: Counter[str] = Counter()
        self.orders_by_symbol: Counter[str] = Counter()
        self.cooldowns_by_symbol: Counter[str] = Counter()

        self.total_decisions = 0
        self.hold_total = 0
        self.candidate_total = 0
        self.selected_total = 0
        self.rejected_total = 0
        self.orders_submitted = 0
        self.orders_failed = 0
        self.orders_filled = 0
        self.positions_opened = 0
        self.positions_closed = 0
        self.positions_restored = 0
        self.force_closed = 0
        self.broker_failures = 0
        self.market_snapshots = 0
        self.candles_closed = 0

        self.gross_pnl_estimated = 0.0
        self.net_pnl_estimated = 0.0
        self.estimated_total_cost = 0.0

        self.top_rejected_candidates: list[dict[str, Any]] = []
        self.selected_candidates: list[dict[str, Any]] = []
        self.session_transitions: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []

    def record(self, event_type: str, payload: dict[str, Any]) -> None:
        self.event_counts[event_type] += 1

        if event_type == 'market_snapshot':
            self.market_snapshots += 1
        elif event_type == 'candle_closed':
            self.candles_closed += 1
        elif event_type == 'candidate_detected':
            self._record_candidate_detected(payload)
        elif event_type == 'candidate_selection':
            self._record_candidate_selection(payload)
        elif event_type == 'decision':
            self._record_decision(payload)
        elif event_type == 'cooldown_blocked':
            self._record_cooldown(payload)
        elif event_type == 'order_submitted':
            self.orders_submitted += 1
            self._increment_symbol_counter(self.orders_by_symbol, payload)
        elif event_type == 'order_failed':
            self.orders_failed += 1
            self._increment_symbol_counter(self.orders_by_symbol, payload)
        elif event_type == 'order_filled':
            self.orders_filled += 1
            self._increment_symbol_counter(self.orders_by_symbol, payload)
        elif event_type == 'position_opened':
            self.positions_opened += 1
        elif event_type == 'position_closed':
            self.positions_closed += 1
            self._record_closed_position_pnl(payload)
        elif event_type == 'position_restored':
            self.positions_restored += 1
        elif event_type in {'force_close_requested', 'force_close_completed', 'force_close'}:
            self.force_closed += 1
        elif event_type == 'session_state_changed':
            self._append_limited(self.session_transitions, self._session_transition_summary(payload))
        elif self._is_error_event(event_type):
            self._record_error(event_type, payload)

    def finalize(self) -> dict[str, Any]:
        self.ended_at = datetime.now(timezone.utc)
        return self.to_dict()

    def write(self, path: str) -> None:
        summary_path = Path(path)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(serialize_value(self.to_dict()), ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': 1,
            'run_id': self.run_id,
            'strategy': self.strategy,
            'profile': self.profile,
            'journal_detail_level': self.journal_detail_level,
            'started_at': self.started_at,
            'ended_at': self.ended_at,
            'events': {
                'by_type': dict(self.event_counts),
            },
            'market_data': {
                'snapshots': self.market_snapshots,
                'candles_closed': self.candles_closed,
            },
            'decisions': {
                'total': self.total_decisions,
                'hold_total': self.hold_total,
                'candidate_total': self.candidate_total,
                'selected_total': self.selected_total,
                'rejected_total': self.rejected_total,
                'orders_submitted': self.orders_submitted,
                'orders_failed': self.orders_failed,
                'orders_filled': self.orders_filled,
            },
            'hold_reasons': dict(self.hold_reasons),
            'rejections': {
                'total': self.rejected_total,
                'by_reason': dict(self.rejection_reasons),
                'top_rejected_candidates': self.top_rejected_candidates,
            },
            'selected_candidates': self.selected_candidates,
            'orders': {
                'submitted': self.orders_submitted,
                'filled': self.orders_filled,
                'failed': self.orders_failed,
                'by_symbol': dict(self.orders_by_symbol),
            },
            'positions': {
                'opened': self.positions_opened,
                'closed': self.positions_closed,
                'restored': self.positions_restored,
                'force_closed': self.force_closed,
            },
            'pnl': {
                'gross_estimated': round(self.gross_pnl_estimated, 4),
                'estimated_total_cost': round(self.estimated_total_cost, 4),
                'net_estimated': round(self.net_pnl_estimated, 4),
            },
            'cooldown': {
                'blocked_total': sum(self.cooldowns_by_symbol.values()),
                'by_symbol': dict(self.cooldowns_by_symbol),
            },
            'runtime': {
                'session_transitions': self.session_transitions,
            },
            'errors': {
                'total': sum(self.error_types.values()),
                'by_type': dict(self.error_types),
                'samples': self.errors,
            },
        }

    def _record_candidate_detected(self, payload: dict[str, Any]) -> None:
        self.candidate_total += 1
        candidate = payload.get('candidate')
        symbol = _attribute(candidate, 'symbol') or payload.get('symbol')
        if symbol:
            self.candidates_by_symbol[str(symbol)] += 1

    def _record_candidate_selection(self, payload: dict[str, Any]) -> None:
        selected = _as_list(payload.get('selected_candidates'))
        rejected = _as_list(payload.get('rejected_candidates'))
        selected_evaluated = _as_list(payload.get('selected_evaluated_candidates'))
        rejected_evaluated = _as_list(payload.get('rejected_evaluated_candidates'))

        selected_source = selected_evaluated or selected
        rejected_source = rejected_evaluated or rejected

        self.selected_total += len(selected_source)
        self.rejected_total += len(rejected_source)

        for selected_item in selected_source:
            self._append_limited(self.selected_candidates, self._selected_candidate_summary(selected_item))

        for rejected_item in rejected_source:
            reason = _attribute(rejected_item, 'reason') or 'unknown_rejection'
            self.rejection_reasons[str(reason)] += 1
            self._remember_top_rejected_candidate(rejected_item, str(reason))

    def _record_decision(self, payload: dict[str, Any]) -> None:
        self.total_decisions += 1
        reason = decision_reason(payload) or 'unknown_decision_reason'

        if is_hold_decision('decision', payload):
            self.hold_total += 1
            self.hold_reasons[reason] += 1
            return

        if is_rejected_decision('decision', payload):
            self.rejected_total += 1
            self.rejection_reasons[reason] += 1
            self._remember_top_rejected_decision(payload, reason)

    def _record_cooldown(self, payload: dict[str, Any]) -> None:
        symbol = payload.get('symbol') or _attribute(payload.get('candidate'), 'symbol')
        if symbol:
            self.cooldowns_by_symbol[str(symbol)] += 1
        reason = payload.get('reason') or _attribute(payload.get('trade_plan'), 'reason') or 'cooldown_blocked'
        self.rejection_reasons[str(reason)] += 1

    def _record_closed_position_pnl(self, payload: dict[str, Any]) -> None:
        closed_position = payload.get('closed_position')
        gross = _attribute(closed_position, 'gross_pnl')
        net = _attribute(closed_position, 'net_pnl_estimated')
        cost = _attribute(closed_position, 'estimated_total_cost')
        if gross is not None:
            self.gross_pnl_estimated += float(gross)
        if net is not None:
            self.net_pnl_estimated += float(net)
        if cost is not None:
            self.estimated_total_cost += float(cost)

    def _record_error(self, event_type: str, payload: dict[str, Any]) -> None:
        self.error_types[event_type] += 1
        if event_type.startswith('broker_'):
            self.broker_failures += 1
        self._append_limited(
            self.errors,
            {
                'event_type': event_type,
                'symbol': payload.get('symbol'),
                'message': payload.get('message'),
            },
        )

    def _remember_top_rejected_decision(self, payload: dict[str, Any], reason: str) -> None:
        item = {
            'symbol': decision_symbol(payload),
            'side': decision_side(payload),
            'score': _candidate_score(payload.get('candidate')),
            'reason': reason,
        }
        self._append_ranked(self.top_rejected_candidates, item)

    def _remember_top_rejected_candidate(self, rejected_item: Any, reason: str) -> None:
        candidate = _candidate_from_selection_item(rejected_item)
        item = _candidate_summary(candidate)
        item['reason'] = reason
        self._append_ranked(self.top_rejected_candidates, item)

    def _selected_candidate_summary(self, selected_item: Any) -> dict[str, Any]:
        return _candidate_summary(_candidate_from_selection_item(selected_item))

    def _session_transition_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            'symbol': payload.get('symbol'),
            'from': payload.get('previous_state'),
            'to': payload.get('new_state'),
            'reason': payload.get('reason'),
            'session_key': payload.get('session_key'),
        }

    def _increment_symbol_counter(self, counter: Counter[str], payload: dict[str, Any]) -> None:
        symbol = payload.get('symbol')
        if symbol:
            counter[str(symbol)] += 1

    def _append_limited(self, items: list[dict[str, Any]], item: dict[str, Any]) -> None:
        if len(items) < self.max_items:
            items.append(item)

    def _append_ranked(self, items: list[dict[str, Any]], item: dict[str, Any]) -> None:
        items.append(item)
        items.sort(key=lambda value: value.get('score') or 0.0, reverse=True)
        del items[self.max_items :]

    def _is_error_event(self, event_type: str) -> bool:
        return (
            event_type == 'error'
            or event_type.endswith('_error')
            or event_type.endswith('_warning')
            or event_type.startswith('broker_')
        )


def _candidate_from_selection_item(item: Any) -> Any:
    if _attribute(item, 'candidate') is not None:
        return _attribute(item, 'candidate')
    evaluated_candidate = _attribute(item, 'evaluated_candidate')
    if evaluated_candidate is not None:
        return _attribute(evaluated_candidate, 'candidate')
    if _attribute(item, 'candidate') is None and _attribute(item, 'score') is not None:
        return item
    return _attribute(item, 'candidate') or item


def _candidate_summary(candidate: Any) -> dict[str, Any]:
    signal = _attribute(candidate, 'signal')
    return {
        'symbol': _attribute(candidate, 'symbol'),
        'side': _attribute(signal, 'action'),
        'score': _candidate_score(candidate),
        'reason': _attribute(candidate, 'rank_reason'),
    }


def _candidate_score(candidate: Any) -> float | None:
    score = _attribute(candidate, 'score')
    if score is None:
        return None
    return float(score)


def _attribute(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return list(value)
