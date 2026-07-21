from collections import Counter
from typing import Any

from app.journal.daily_summary import DailySummaryAggregator


class AnalysisReadySummaryAggregator(DailySummaryAggregator):
    """Summary schema focused on post-run calibration."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.validated_accepted_total = 0
        self.tp_hard_rejection_components = Counter()
        self.effective_sl_tp_sources = Counter()
        self.market_context_score_buckets = Counter()
        self.multi_timeframe_score_buckets = Counter()
        self.tp_feasibility_score_buckets = Counter()
        self.tp_feasibility_contribution_buckets = Counter()
        self.entry_freshness_score_buckets = Counter()
        self.net_expected_value_buckets = Counter()
        self.calibration_profiles = Counter()
        self.entry_horizon_rejections_by_profile = Counter()
        self.entry_horizon_rejections_by_reason = Counter()
        self.managed_stop_updates_by_type = Counter()

    def record(self, event_type: str, payload: dict[str, Any]) -> None:
        super().record(event_type, payload)
        if event_type == 'market_data_event_received':
            self.market_data_received += 1
        elif event_type == 'market_price_changed':
            self.market_snapshots += 1
            self.market_data_accepted += 1
        elif event_type == 'candle_finalized':
            self.candles_closed += 1
        elif event_type == 'market_batch_validated':
            batch = payload.get('batch')
            accepted = _attribute(batch, 'accepted') or {}
            self.validated_accepted_total += len(accepted)
        elif event_type == 'candidate_tp_feasibility':
            self._record_candidate_scores(payload)
        elif event_type == 'entry_horizon_rejected':
            self.entry_horizon_rejections_by_reason[
                str(payload.get('reason') or 'unknown')
            ] += 1
            self.entry_horizon_rejections_by_profile[
                str(payload.get('profile_key') or 'unknown')
            ] += 1
        elif event_type == 'managed_stop_updated':
            self.managed_stop_updates_by_type[
                str(payload.get('protection_type') or 'unknown')
            ] += 1
        elif event_type == 'position_close_confirmed':
            self.positions_closed += 1
            self._record_closed_position_pnl(payload)

    def _record_decision(self, payload):
        approved_before = self.risk_approved
        rejected_before = self.risk_rejected
        super()._record_decision(payload)
        if payload.get('candidate') is None:
            self.risk_approved = approved_before
            self.risk_rejected = rejected_before

    def _record_candidate_scores(self, payload: dict[str, Any]) -> None:
        for item in _as_list(payload.get('evaluated_candidates')):
            analysis = _attribute(item, 'tp_feasibility')
            probability = _attribute(item, 'tp_probability')
            candidate = _attribute(item, 'candidate')
            effective_sl_tp = _attribute(item, 'effective_sl_tp')
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
            calibration_profile = _attribute(
                probability,
                'calibration_profile_key',
            )
            if calibration_profile:
                self.calibration_profiles[str(calibration_profile)] += 1
            self._record_bucket(
                self.market_context_score_buckets,
                _attribute(candidate, 'market_context_score'),
                width=5.0,
            )
            self._record_bucket(
                self.multi_timeframe_score_buckets,
                _attribute(candidate, 'multi_timeframe_score'),
                width=2.0,
            )
            self._record_bucket(
                self.tp_feasibility_score_buckets,
                _attribute(analysis, 'feasibility_score'),
                width=10.0,
            )
            self._record_bucket(
                self.tp_feasibility_contribution_buckets,
                _attribute(analysis, 'score_contribution'),
                width=5.0,
            )
            self._record_bucket(
                self.entry_freshness_score_buckets,
                _attribute(analysis, 'entry_freshness_score'),
                width=10.0,
            )
            self._record_bucket(
                self.net_expected_value_buckets,
                _attribute(candidate, 'net_expected_value_percent'),
                width=0.25,
            )

    def _record_bucket(
        self,
        counter: Counter,
        value: Any,
        *,
        width: float,
    ) -> None:
        if value is None:
            counter['unavailable'] += 1
            return
        numeric = float(value)
        lower = (numeric // width) * width
        upper = lower + width
        counter[f'[{lower:.2f},{upper:.2f})'] += 1

    def to_dict(self) -> dict[str, Any]:
        summary = super().to_dict()
        summary['schema_version'] = 8
        market_data = summary['market_data']
        trading_snapshots = market_data.get('accepted', 0)
        market_data['trading_snapshots_processed'] = trading_snapshots
        accepted_total = self.validated_accepted_total or trading_snapshots
        market_data['accepted'] = accepted_total
        market_data['context_snapshots_accepted'] = max(
            0,
            accepted_total - trading_snapshots,
        )
        summary['score_contributions'] = {
            'market_context': dict(self.market_context_score_buckets),
            'multi_timeframe': dict(self.multi_timeframe_score_buckets),
            'tp_feasibility_score': dict(self.tp_feasibility_score_buckets),
            'tp_feasibility_contribution': dict(
                self.tp_feasibility_contribution_buckets
            ),
            'entry_freshness_score': dict(self.entry_freshness_score_buckets),
            'net_expected_value_percent': dict(self.net_expected_value_buckets),
        }
        summary['tp_feasibility'] = {
            'hard_rejection_components': dict(
                self.tp_hard_rejection_components
            ),
        }
        summary['effective_sl_tp'] = {
            'by_source': dict(self.effective_sl_tp_sources),
        }
        summary['tp_probability'] = {
            'by_calibration_profile': dict(self.calibration_profiles),
        }
        summary['entry_horizon'] = {
            'rejections_by_reason': dict(
                self.entry_horizon_rejections_by_reason
            ),
            'rejections_by_profile': dict(
                self.entry_horizon_rejections_by_profile
            ),
        }
        summary['managed_stops'] = {
            'updates_by_type': dict(self.managed_stop_updates_by_type),
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
