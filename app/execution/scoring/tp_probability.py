from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from app.execution.candidate_economics import EvaluatedTradeCandidate
from app.execution.scoring.tp_feasibility import TpFeasibilityAnalysis
from app.execution.trade_candidate import TradeCandidate


TP_PROBABILITY_MODEL_VERSION = 'heuristic_v5'


@dataclass(frozen=True)
class TpProbabilityConfig:
    min_probability: float = 0.05
    max_probability: float = 0.85
    raw_base_probability: float = 0.20
    raw_probability_range: float = 0.60
    calibration_slope: float = 0.35
    calibration_base_rates: dict[str, float] | None = None
    good_cost_to_tp_ratio: float = 0.10
    bad_cost_to_tp_ratio: float = 0.65
    good_tp_to_atr_ratio: float = 1.50
    bad_tp_to_atr_ratio: float = 6.00
    good_tp_to_momentum_ratio: float = 3.00
    bad_tp_to_momentum_ratio: float = 12.00
    weak_trend_strength_percent: float = 0.05
    strong_trend_strength_percent: float = 0.30
    weak_close_quality_percent: float = 55.0
    strong_close_quality_percent: float = 90.0
    maximum_context_score: float = 4.0
    maximum_multi_timeframe_score: float = 3.0

    def base_rate_for(self, profile_key: str) -> float:
        rates = self.calibration_base_rates or {
            'us_intraday_fixed_v1:BUY': 0.45,
            'us_intraday_fixed_v1:SELL': 0.18,
            'eu_trend_buy_v1:BUY': 0.33,
            'eu_intraday_fixed_v1:BUY': 0.35,
            'eu_intraday_fixed_v1:SELL': 0.35,
            'crypto_intraday_fixed_v1:BUY': 0.25,
            'crypto_intraday_fixed_v1:SELL': 0.15,
        }
        return rates.get(profile_key, 0.35)


@dataclass(frozen=True)
class TpBeforeSlProbabilityEstimate:
    raw_probability: float
    tp_before_sl_probability: float
    probability_band: str
    model_version: str
    raw_score: float
    calibration_profile_key: str
    calibration_base_rate: float
    calibration_slope: float
    break_even_probability: float
    net_expected_value_percent: float
    probability_edge: float
    component_scores: dict[str, float]
    reason_components: tuple[str, ...]
    missing_components: tuple[str, ...]


class TpBeforeSlProbabilityEstimator:
    def __init__(self, config: TpProbabilityConfig | None = None):
        self.config = config or TpProbabilityConfig()

    def estimate(
        self,
        *,
        evaluated_candidate: EvaluatedTradeCandidate,
        tp_feasibility: TpFeasibilityAnalysis,
    ) -> TpBeforeSlProbabilityEstimate:
        candidate = evaluated_candidate.candidate
        metadata = candidate.signal.metadata or {}
        missing: list[str] = []
        scores = {
            'cost_score': self._high_is_bad(
                'cost_to_tp_ratio', tp_feasibility.cost_to_tp_ratio,
                self.config.good_cost_to_tp_ratio,
                self.config.bad_cost_to_tp_ratio, missing,
            ),
            'atr_distance_score': self._high_is_bad(
                'tp_to_atr_ratio', tp_feasibility.tp_to_atr_ratio,
                self.config.good_tp_to_atr_ratio,
                self.config.bad_tp_to_atr_ratio, missing,
            ),
            'momentum_distance_score': self._high_is_bad(
                'tp_to_snapshot_momentum_ratio',
                tp_feasibility.tp_to_snapshot_momentum_ratio,
                self.config.good_tp_to_momentum_ratio,
                self.config.bad_tp_to_momentum_ratio, missing,
            ),
            'trend_score': self._low_is_bad(
                'trend_strength_percent',
                abs(_optional_float(metadata.get('trend_strength_percent')) or 0.0),
                self.config.weak_trend_strength_percent,
                self.config.strong_trend_strength_percent, missing,
            ),
            'close_quality_score': self._low_is_bad(
                'close_quality', _close_quality(candidate),
                self.config.weak_close_quality_percent,
                self.config.strong_close_quality_percent, missing,
            ),
            'regime_score': _market_regime_score(metadata),
            'market_context_score': _centered_score(
                candidate.market_context_score,
                self.config.maximum_context_score,
            ),
            'multi_timeframe_score': _centered_score(
                candidate.multi_timeframe_score,
                self.config.maximum_multi_timeframe_score,
            ),
        }
        raw_score = (
            0.20 * scores['cost_score']
            + 0.17 * scores['atr_distance_score']
            + 0.22 * scores['momentum_distance_score']
            + 0.14 * scores['trend_score']
            + 0.10 * scores['close_quality_score']
            + 0.07 * scores['regime_score']
            + 0.04 * scores['market_context_score']
            + 0.06 * scores['multi_timeframe_score']
        )
        raw_probability = _bounded(
            self.config.raw_base_probability
            + self.config.raw_probability_range * raw_score / 100.0,
            self.config.min_probability,
            self.config.max_probability,
        )
        profile_key = _calibration_profile_key(
            evaluated_candidate, tp_feasibility
        )
        base_rate = self.config.base_rate_for(profile_key)
        calibrated = _bounded(
            base_rate
            + self.config.calibration_slope * (raw_probability - 0.50),
            self.config.min_probability,
            self.config.max_probability,
        )
        break_even, net_ev, edge = _net_expectancy(
            probability=calibrated,
            expected_net_gain_percent=(
                evaluated_candidate.economics.expected_net_profit_percent
            ),
            stop_loss_percent=tp_feasibility.effective_stop_loss_percent,
            estimated_cost_percent=(
                evaluated_candidate.economics.estimated_total_cost_percent
            ),
        )
        rounded = {name: round(value, 4) for name, value in scores.items()}
        reasons = _reason_components(rounded)
        reasons.extend(
            f'tp_feasibility:{reason}'
            for reason in tp_feasibility.reason_components
        )
        return TpBeforeSlProbabilityEstimate(
            raw_probability=round(raw_probability, 4),
            tp_before_sl_probability=round(calibrated, 4),
            probability_band=_probability_band(calibrated),
            model_version=TP_PROBABILITY_MODEL_VERSION,
            raw_score=round(raw_score, 4),
            calibration_profile_key=profile_key,
            calibration_base_rate=round(base_rate, 4),
            calibration_slope=round(self.config.calibration_slope, 4),
            break_even_probability=round(break_even, 4),
            net_expected_value_percent=round(net_ev, 4),
            probability_edge=round(edge, 4),
            component_scores=rounded,
            reason_components=tuple(reasons),
            missing_components=tuple(missing),
        )

    @staticmethod
    def _high_is_bad(name, value, good, bad, missing):
        if value is None:
            missing.append(name)
            return 45.0
        if value <= good:
            return 100.0
        if value >= bad:
            return 0.0
        return 100.0 * (1.0 - ((value - good) / (bad - good)))

    @staticmethod
    def _low_is_bad(name, value, weak, strong, missing):
        if value is None:
            missing.append(name)
            return 45.0
        if value <= weak:
            return 0.0
        if value >= strong:
            return 100.0
        return 100.0 * ((value - weak) / (strong - weak))


class CandidateTpProbabilityEvaluator:
    def __init__(self, estimator: TpBeforeSlProbabilityEstimator | None = None):
        self.estimator = estimator or TpBeforeSlProbabilityEstimator()

    def evaluate(self, evaluated_candidate: EvaluatedTradeCandidate):
        if evaluated_candidate.tp_feasibility is None:
            return evaluated_candidate
        estimate = self.estimator.estimate(
            evaluated_candidate=evaluated_candidate,
            tp_feasibility=evaluated_candidate.tp_feasibility,
        )
        candidate = evaluated_candidate.candidate
        updated = replace(
            candidate,
            rank_reason=_append_rank_reason(candidate.rank_reason, estimate),
            raw_tp_before_sl_probability=estimate.raw_probability,
            tp_before_sl_probability=estimate.tp_before_sl_probability,
            tp_before_sl_probability_band=estimate.probability_band,
            tp_probability_model_version=estimate.model_version,
            break_even_probability=estimate.break_even_probability,
            net_expected_value_percent=estimate.net_expected_value_percent,
            probability_edge=estimate.probability_edge,
            tp_probability_metadata=estimate_to_metadata(estimate),
        )
        return replace(
            evaluated_candidate,
            candidate=updated,
            tp_probability=estimate,
        )


def estimate_to_metadata(estimate: TpBeforeSlProbabilityEstimate) -> dict[str, Any]:
    return {
        'raw_tp_before_sl_probability': estimate.raw_probability,
        'tp_before_sl_probability': estimate.tp_before_sl_probability,
        'tp_before_sl_probability_band': estimate.probability_band,
        'tp_probability_model_version': estimate.model_version,
        'tp_probability_raw_score': estimate.raw_score,
        'calibration_profile_key': estimate.calibration_profile_key,
        'calibration_base_rate': estimate.calibration_base_rate,
        'calibration_slope': estimate.calibration_slope,
        'break_even_probability': estimate.break_even_probability,
        'net_expected_value_percent': estimate.net_expected_value_percent,
        'probability_edge': estimate.probability_edge,
        'tp_probability_component_scores': estimate.component_scores,
        'tp_probability_reason_components': list(estimate.reason_components),
        'tp_probability_missing_components': list(estimate.missing_components),
    }


def _append_rank_reason(rank_reason, estimate):
    suffix = (
        f'raw_tp_before_sl_probability={estimate.raw_probability:.4f},'
        f'tp_before_sl_probability={estimate.tp_before_sl_probability:.4f},'
        f'calibration_profile={estimate.calibration_profile_key},'
        f'break_even_probability={estimate.break_even_probability:.4f},'
        f'net_expected_value_percent={estimate.net_expected_value_percent:.4f},'
        f'probability_edge={estimate.probability_edge:.4f},'
        f'tp_probability_band={estimate.probability_band},'
        f'tp_probability_model={estimate.model_version}'
    )
    return f'{rank_reason};{suffix}' if rank_reason else suffix


def _calibration_profile_key(evaluated_candidate, tp_feasibility):
    source = tp_feasibility.sl_tp_source
    effective = evaluated_candidate.effective_sl_tp
    if source == 'pending_structural' and effective is not None:
        source = str(effective.metadata.get('baseline_sl_tp_source') or source)
    side = evaluated_candidate.candidate.signal.action.strip().upper()
    return f'{source}:{side}'


def _net_expectancy(*, probability, expected_net_gain_percent,
                    stop_loss_percent, estimated_cost_percent):
    net_gain = max(float(expected_net_gain_percent), 0.0)
    net_loss = max(float(stop_loss_percent) + float(estimated_cost_percent), 0.0)
    total = net_gain + net_loss
    break_even = net_loss / total if total > 0 else 1.0
    net_ev = probability * net_gain - (1.0 - probability) * net_loss
    return break_even, net_ev, probability - break_even


def _centered_score(value, maximum_absolute):
    if value is None or maximum_absolute <= 0:
        return 50.0
    bounded = _bounded(float(value), -maximum_absolute, maximum_absolute)
    return (bounded + maximum_absolute) * 100.0 / (2.0 * maximum_absolute)


def _close_quality(candidate: TradeCandidate):
    close_position = _optional_float(
        (candidate.signal.metadata or {}).get('close_position_percent')
    )
    if close_position is None:
        return None
    return 100.0 - close_position if candidate.signal.action == 'SELL' else close_position


def _market_regime_score(metadata):
    return {
        'TRENDING': 100.0,
        'RANGING': 35.0,
        'DEAD_MARKET': 20.0,
    }.get(str(metadata.get('market_regime', '')).upper(), 50.0)


def _reason_components(scores):
    reasons = []
    for name, score in scores.items():
        suffix = 'weak' if score < 35.0 else 'strong' if score >= 75.0 else 'neutral'
        reasons.append(f'{name}_{suffix}')
    return reasons


def _probability_band(probability):
    if probability < 0.35:
        return 'LOW'
    if probability < 0.50:
        return 'MEDIUM_LOW'
    if probability < 0.65:
        return 'MEDIUM_HIGH'
    return 'HIGH'


def _optional_float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _bounded(value, minimum, maximum):
    return max(minimum, min(maximum, value))
