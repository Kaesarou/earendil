from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from app.execution.candidate_economics import EvaluatedTradeCandidate
from app.execution.trade_candidate import TradeCandidate

if TYPE_CHECKING:
    from app.execution.scoring.tp_feasibility import TpFeasibilityAnalysis

TP_PROBABILITY_MODEL_VERSION = 'heuristic_v2'


@dataclass(frozen=True)
class TpProbabilityConfig:
    min_probability: float = 0.05
    max_probability: float = 0.85
    base_probability: float = 0.20
    probability_range: float = 0.60
    good_cost_to_tp_ratio: float = 0.10
    bad_cost_to_tp_ratio: float = 0.65
    good_tp_to_atr_ratio: float = 1.50
    bad_tp_to_atr_ratio: float = 6.00
    good_tp_to_momentum_ratio: float = 3.00
    bad_tp_to_momentum_ratio: float = 12.00
    good_movement_consumed_percent: float = 0.50
    bad_movement_consumed_percent: float = 2.00
    weak_trend_strength_percent: float = 0.05
    strong_trend_strength_percent: float = 0.30
    weak_close_quality_percent: float = 55.0
    strong_close_quality_percent: float = 90.0


@dataclass(frozen=True)
class TpBeforeSlProbabilityEstimate:
    tp_before_sl_probability: float
    probability_band: str
    model_version: str
    raw_score: float
    break_even_probability: float
    net_expected_value_percent: float
    probability_edge: float
    component_scores: dict[str, float | None]
    reason_components: tuple[str, ...]
    missing_components: tuple[str, ...]


class TpBeforeSlProbabilityEstimator:
    def __init__(self, config: TpProbabilityConfig | None = None):
        self.config = config or TpProbabilityConfig()

    def estimate(
        self,
        *,
        evaluated_candidate: EvaluatedTradeCandidate,
        tp_feasibility: 'TpFeasibilityAnalysis',
    ) -> TpBeforeSlProbabilityEstimate:
        candidate = evaluated_candidate.candidate
        metadata = candidate.signal.metadata or {}
        missing_components: list[str] = []
        reason_components: list[str] = []

        feasibility_score = _bounded(
            tp_feasibility.runway_score,
            0.0,
            100.0,
        )
        cost_score = self._score_high_value_is_bad(
            name='cost_to_tp_ratio',
            value=tp_feasibility.cost_to_tp_ratio,
            good=self.config.good_cost_to_tp_ratio,
            bad=self.config.bad_cost_to_tp_ratio,
            missing_components=missing_components,
        )
        atr_distance_score = self._score_high_value_is_bad(
            name='tp_to_atr_ratio',
            value=tp_feasibility.tp_to_atr_ratio,
            good=self.config.good_tp_to_atr_ratio,
            bad=self.config.bad_tp_to_atr_ratio,
            missing_components=missing_components,
        )
        momentum_distance_score = self._score_high_value_is_bad(
            name='tp_to_snapshot_momentum_ratio',
            value=tp_feasibility.tp_to_snapshot_momentum_ratio,
            good=self.config.good_tp_to_momentum_ratio,
            bad=self.config.bad_tp_to_momentum_ratio,
            missing_components=missing_components,
        )
        movement_freshness_score = self._score_high_value_is_bad(
            name='movement_consumed_percent',
            value=tp_feasibility.movement_consumed_percent,
            good=self.config.good_movement_consumed_percent,
            bad=self.config.bad_movement_consumed_percent,
            missing_components=missing_components,
        )
        trend_score = self._score_low_value_is_bad(
            name='trend_strength_percent',
            value=abs(
                _optional_float(metadata.get('trend_strength_percent'))
                or 0.0
            ),
            weak=self.config.weak_trend_strength_percent,
            strong=self.config.strong_trend_strength_percent,
            missing_components=missing_components,
        )
        close_quality_score = self._score_low_value_is_bad(
            name='close_quality',
            value=_close_quality(candidate),
            weak=self.config.weak_close_quality_percent,
            strong=self.config.strong_close_quality_percent,
            missing_components=missing_components,
        )
        regime_score = _market_regime_score(metadata)

        component_scores = {
            'feasibility_score': round(feasibility_score, 4),
            'cost_score': round(cost_score, 4),
            'atr_distance_score': round(atr_distance_score, 4),
            'momentum_distance_score': round(momentum_distance_score, 4),
            'movement_freshness_score': round(
                movement_freshness_score,
                4,
            ),
            'trend_score': round(trend_score, 4),
            'close_quality_score': round(close_quality_score, 4),
            'regime_score': round(regime_score, 4),
        }

        raw_score = (
            0.24 * feasibility_score
            + 0.18 * momentum_distance_score
            + 0.14 * atr_distance_score
            + 0.12 * cost_score
            + 0.10 * trend_score
            + 0.08 * close_quality_score
            + 0.08 * movement_freshness_score
            + 0.06 * regime_score
        )
        probability = self.config.base_probability + (
            self.config.probability_range * (raw_score / 100)
        )
        probability = _bounded(
            probability,
            self.config.min_probability,
            self.config.max_probability,
        )
        break_even_probability, net_expected_value, probability_edge = (
            _net_expectancy(
                probability=probability,
                expected_net_gain_percent=(
                    evaluated_candidate.economics.expected_net_profit_percent
                ),
                stop_loss_percent=(
                    tp_feasibility.effective_stop_loss_percent
                ),
                estimated_cost_percent=(
                    evaluated_candidate.economics.estimated_total_cost_percent
                ),
            )
        )

        reason_components.extend(
            _probability_reason_components(component_scores)
        )
        if tp_feasibility.reason_components:
            reason_components.extend(
                f'tp_feasibility:{component}'
                for component in tp_feasibility.reason_components
            )

        return TpBeforeSlProbabilityEstimate(
            tp_before_sl_probability=round(probability, 4),
            probability_band=_probability_band(probability),
            model_version=TP_PROBABILITY_MODEL_VERSION,
            raw_score=round(raw_score, 4),
            break_even_probability=round(break_even_probability, 4),
            net_expected_value_percent=round(net_expected_value, 4),
            probability_edge=round(probability_edge, 4),
            component_scores=component_scores,
            reason_components=tuple(reason_components),
            missing_components=tuple(missing_components),
        )

    def _score_high_value_is_bad(
        self,
        *,
        name: str,
        value: float | None,
        good: float,
        bad: float,
        missing_components: list[str],
    ) -> float:
        if value is None:
            missing_components.append(name)
            return 45.0
        if value <= good:
            return 100.0
        if value >= bad:
            return 0.0
        return 100.0 * (1.0 - ((value - good) / (bad - good)))

    def _score_low_value_is_bad(
        self,
        *,
        name: str,
        value: float | None,
        weak: float,
        strong: float,
        missing_components: list[str],
    ) -> float:
        if value is None:
            missing_components.append(name)
            return 45.0
        if value <= weak:
            return 0.0
        if value >= strong:
            return 100.0
        return 100.0 * ((value - weak) / (strong - weak))


class CandidateTpProbabilityEvaluator:
    def __init__(
        self,
        estimator: TpBeforeSlProbabilityEstimator | None = None,
    ):
        self.estimator = estimator or TpBeforeSlProbabilityEstimator()

    def evaluate(
        self,
        evaluated_candidate: EvaluatedTradeCandidate,
    ) -> EvaluatedTradeCandidate:
        if evaluated_candidate.tp_feasibility is None:
            return evaluated_candidate

        estimate = self.estimator.estimate(
            evaluated_candidate=evaluated_candidate,
            tp_feasibility=evaluated_candidate.tp_feasibility,
        )
        candidate = evaluated_candidate.candidate
        updated_candidate = replace(
            candidate,
            rank_reason=_append_rank_reason(candidate.rank_reason, estimate),
            tp_before_sl_probability=estimate.tp_before_sl_probability,
            tp_before_sl_probability_band=estimate.probability_band,
            tp_probability_model_version=estimate.model_version,
            break_even_probability=estimate.break_even_probability,
            net_expected_value_percent=(
                estimate.net_expected_value_percent
            ),
            probability_edge=estimate.probability_edge,
            tp_probability_metadata=estimate_to_metadata(estimate),
        )
        return replace(
            evaluated_candidate,
            candidate=updated_candidate,
            tp_probability=estimate,
        )


def estimate_to_metadata(
    estimate: TpBeforeSlProbabilityEstimate,
) -> dict[str, Any]:
    return {
        'tp_before_sl_probability': estimate.tp_before_sl_probability,
        'tp_before_sl_probability_band': estimate.probability_band,
        'tp_probability_model_version': estimate.model_version,
        'tp_probability_raw_score': estimate.raw_score,
        'break_even_probability': estimate.break_even_probability,
        'net_expected_value_percent': estimate.net_expected_value_percent,
        'probability_edge': estimate.probability_edge,
        'tp_probability_component_scores': estimate.component_scores,
        'tp_probability_reason_components': list(
            estimate.reason_components
        ),
        'tp_probability_missing_components': list(
            estimate.missing_components
        ),
    }


def _append_rank_reason(
    rank_reason: str,
    estimate: TpBeforeSlProbabilityEstimate,
) -> str:
    suffix = (
        f'tp_before_sl_probability='
        f'{estimate.tp_before_sl_probability:.2f},'
        f'break_even_probability={estimate.break_even_probability:.2f},'
        f'net_expected_value_percent='
        f'{estimate.net_expected_value_percent:.4f},'
        f'probability_edge={estimate.probability_edge:.4f},'
        f'tp_probability_band={estimate.probability_band},'
        f'tp_probability_model={estimate.model_version}'
    )
    return f'{rank_reason};{suffix}' if rank_reason else suffix


def _net_expectancy(
    *,
    probability: float,
    expected_net_gain_percent: float,
    stop_loss_percent: float,
    estimated_cost_percent: float,
) -> tuple[float, float, float]:
    net_gain = max(float(expected_net_gain_percent), 0.0)
    net_loss = max(
        float(stop_loss_percent) + float(estimated_cost_percent),
        0.0,
    )
    total_outcome = net_gain + net_loss
    break_even_probability = (
        net_loss / total_outcome
        if total_outcome > 0
        else 1.0
    )
    net_expected_value = (
        probability * net_gain
        - (1.0 - probability) * net_loss
    )
    return (
        break_even_probability,
        net_expected_value,
        probability - break_even_probability,
    )


def _close_quality(candidate: TradeCandidate) -> float | None:
    metadata = candidate.signal.metadata or {}
    close_position_percent = _optional_float(
        metadata.get('close_position_percent')
    )
    if close_position_percent is None:
        return None
    if candidate.signal.action == 'SELL':
        return 100.0 - close_position_percent
    if candidate.signal.action == 'BUY':
        return close_position_percent
    return None


def _market_regime_score(metadata: dict[str, Any]) -> float:
    regime = str(metadata.get('market_regime', '')).upper()
    if regime == 'TRENDING':
        return 100.0
    if regime == 'RANGING':
        return 35.0
    if regime == 'DEAD_MARKET':
        return 20.0
    return 50.0


def _probability_reason_components(
    component_scores: dict[str, float | None],
) -> list[str]:
    components: list[str] = []
    for name, score in component_scores.items():
        if score is None:
            continue
        if score < 35.0:
            components.append(f'{name}_weak')
        elif score >= 75.0:
            components.append(f'{name}_strong')
    return components


def _probability_band(probability: float) -> str:
    if probability < 0.30:
        return 'VERY_LOW'
    if probability < 0.45:
        return 'LOW'
    if probability < 0.55:
        return 'MEDIUM'
    if probability < 0.65:
        return 'GOOD'
    return 'HIGH'


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounded(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))
