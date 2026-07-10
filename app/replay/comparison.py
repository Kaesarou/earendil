from collections import Counter
from typing import Any

from app.replay.dataset import ReplayDataset


def build_replay_comparison(
    dataset: ReplayDataset,
    replay_report: dict[str, Any],
) -> dict[str, Any]:
    actual_candidates: dict[str, dict[str, Any]] = {}
    actual_selected: set[str] = set()
    rejection_reasons: Counter[str] = Counter()

    for record in dataset.trade_records():
        if record.event_type == 'candidate_detected':
            candidate = _candidate_from_payload(record.payload.get('candidate'))
            if candidate is not None:
                actual_candidates[candidate['key']] = candidate
        elif record.event_type == 'candidate_selection':
            for selected in record.payload.get('selected_candidates') or []:
                candidate = _candidate_from_payload(selected)
                if candidate is not None:
                    actual_selected.add(candidate['key'])
            for rejected in record.payload.get('rejected_candidates') or []:
                reason = _attribute(rejected, 'reason') or 'unknown_rejection'
                rejection_reasons[str(reason)] += 1

    simulated_candidates = {
        candidate['key']: candidate
        for candidate in replay_report.get('candidates', [])
    }
    actual_keys = set(actual_candidates)
    simulated_keys = set(simulated_candidates)
    additional_keys = sorted(simulated_keys - actual_keys)
    missing_keys = sorted(actual_keys - simulated_keys)
    matched_keys = sorted(actual_keys & simulated_keys)

    return {
        'schema_version': 1,
        'run_id': dataset.run_id,
        'baseline': {
            'candidate_total': len(actual_candidates),
            'selected_total': len(actual_selected),
            'rejection_reasons': dict(rejection_reasons),
        },
        'simulation': {
            'candidate_total': len(simulated_candidates),
        },
        'comparison': {
            'matched_candidates': len(matched_keys),
            'additional_simulated_candidates': [
                simulated_candidates[key]
                for key in additional_keys
            ],
            'missing_simulated_candidates': [
                actual_candidates[key]
                for key in missing_keys
            ],
            'potential_missed_opportunities': [
                simulated_candidates[key]
                for key in additional_keys
                if simulated_candidates[key]
                .get('counterfactual_outcome', {})
                .get('status') == 'TP'
            ],
            'additional_simulated_losses': [
                simulated_candidates[key]
                for key in additional_keys
                if simulated_candidates[key]
                .get('counterfactual_outcome', {})
                .get('status') == 'SL'
            ],
        },
        'limitations': [
            'Counterfactual outcomes use snapshot.last and static SL/TP profile percentages.',
            'Fees, broker slippage, position overlap, cooldown and account-equity constraints are not applied.',
            'A code commit mismatch means the replay is a strategy comparison, not an exact reproduction.',
        ],
    }


def _candidate_from_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    symbol = value.get('symbol')
    signal = value.get('signal') or {}
    candle = value.get('candle') or {}
    side = _attribute(signal, 'action')
    closed_at = _attribute(candle, 'closed_at')
    if not symbol or not side or not closed_at:
        return None
    return {
        'key': f'{symbol}|{side}|{closed_at}',
        'symbol': symbol,
        'side': side,
        'score': value.get('score'),
        'closed_at': closed_at,
        'reason': value.get('rank_reason'),
    }


def _attribute(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)
