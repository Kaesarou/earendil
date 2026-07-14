from collections import Counter
from typing import Any

from app.journal.daily_summary import DailySummaryAggregator


class AnalysisReadySummaryAggregator(DailySummaryAggregator):
    """Summary schema focused on post-run calibration and counterfactual analysis."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.validated_accepted_total = 0
        self.tp_penalty_components = Counter()
        self.tp_cap_components = Counter()
        self.tp_hard_rejection_components = Counter()
        self.effective_sl_tp_sources = Counter()
        self.candidate_adaptations = Counter()

    def record(self, event_type: str, payload: dict[str, Any]) -> None:
        super().record(event_type, payload)
        if event_type == 'market_batch_validated':
            batch = payload.get('batch')
            accepted = _attribute(batch, 'accepted') or {}
            self.validated_accepted_total += len(accepted)
        elif event_type == 'candidate_tp_feasibility':
            self._record_tp_feasibility(payload)

    def _record_tp_feasibility(self, payload: dict[str, Any]) -> None:
        for item in _as_list(payload.get('evaluated_candidates')):
            analysis = _attribute(item, 'tp_feasibility')
            candidate = _attribute(item, 'candidate')
            effective_sl_tp = _attribute(item, 'effective_sl_tp')
            for component in _as_list(_attribute(analysis, 'penalty_components')):
                self.tp_penalty_components[str(component)] += 1
            for component in _as_list(_attribute(analysis, 'cap_components')):
                self.tp_cap_components[str(component)] += 1
            for component in _as_list(
                _attribute(analysis, 'hard_rejection_components')
            ):
                self.tp_hard_rejection_components[str(component)] += 1
            source = _attribute(effective_sl_tp, 'source') or _attribute(
                analysis,
                'sl_tp_source',
            )
            if source:
                self.effective_sl_tp_sources[str(source)] += 1
            metadata = _attribute(candidate, 'tp_feasibility_metadata') or {}
            adaptation = _attribute(metadata, 'adaptation')
            if adaptation:
                self.candidate_adaptations[str(adaptation)] += 1

    def to_dict(self) -> dict[str, Any]:
        summary = super().to_dict()
        market_data = summary['market_data']
        trading_snapshots = market_data.get('accepted', 0)
        market_data['trading_snapshots_processed'] = trading_snapshots
        accepted_total = self.validated_accepted_total or trading_snapshots
        market_data['accepted'] = accepted_total
        market_data['context_snapshots_accepted'] = max(
            0,
            accepted_total - trading_snapshots,
        )
        summary['tp_feasibility'] = {
            'penalty_components': dict(self.tp_penalty_components),
            'cap_components': dict(self.tp_cap_components),
            'hard_rejection_components': dict(
                self.tp_hard_rejection_components
            ),
        }
        summary['effective_sl_tp'] = {
            'by_source': dict(self.effective_sl_tp_sources),
            'adaptations': dict(self.candidate_adaptations),
        }
        return summary


def _attribute(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return list(value)
