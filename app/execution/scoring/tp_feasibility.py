from dataclasses import dataclass, replace
from typing import Any

from app.execution.candidate_economics import EvaluatedTradeCandidate
from app.execution.candidate_readiness import (
    CandidateReadiness,
    evaluate_candidate_readiness,
)
from app.execution.sl_tp_profile import EffectiveSlTpResolver
from app.execution.trade_candidate import TradeCandidate
from app.instruments.models import RiskProfile, TpFeasibilityConfig

TP_FEASIBILITY_HARD_REJECTION_PREFIX = 'candidate_selection_tp_feasibility_'


@dataclass(frozen=True)
class TpFeasibilityAnalysis:
    effective_take_profit_percent: float
    effective_stop_loss_percent: float
    atr_percent: float | None
    snapshot_momentum_percent: float | None
    directional_snapshot_momentum_percent: float | None
    session_move_percent: float | None
    directional_session_move_percent: float | None
    tp_to_atr_ratio: float | None
    tp_to_snapshot_momentum_ratio: float | None
    required_net_move_percent: float
    cost_to_tp_ratio: float
    reward_to_risk_ratio: float
    net_reward_to_risk_ratio: float
    sl_tp_mode: str
    sl_tp_source: str
    distance_to_trade_extreme_percent: float | None
    movement_consumed_percent: float | None
    runway_score: float
    raw_runway_score: float
    score_before_tp_feasibility: float
    adjusted_score: float
    tp_feasibility_penalty: float
    raw_tp_feasibility_penalty: float
    tp_feasibility_hard_rejection_reason: str | None
    readiness: CandidateReadiness
    readiness_reason: str
    penalty_components: tuple[str, ...]
    hard_rejection_components: tuple[str, ...]
    reason_components: tuple[str, ...]


class TpFeasibilityAnalyzer:
    def __init__(self, sl_tp_resolver: EffectiveSlTpResolver | None = None):
        self.sl_tp_resolver = sl_tp_resolver or EffectiveSlTpResolver()

    def analyze(
        self,
        *,
        evaluated_candidate: EvaluatedTradeCandidate,
        risk_profile: RiskProfile,
    ) -> TpFeasibilityAnalysis:
        candidate = evaluated_candidate.candidate
        config = risk_profile.tp_feasibility
        if not config.enabled:
            return self._disabled_analysis(
                evaluated_candidate=evaluated_candidate,
                risk_profile=risk_profile,
            )

        metadata = candidate.signal.metadata or {}
        side = candidate.signal.action
        effective_sl_tp = (
            evaluated_candidate.effective_sl_tp
            or self.sl_tp_resolver.resolve_for_signal(
                signal=candidate.signal,
                risk_profile=risk_profile,
            )
        )
        effective_take_profit_percent = effective_sl_tp.take_profit_percent
        effective_stop_loss_percent = effective_sl_tp.stop_loss_percent
        atr_percent = effective_sl_tp.atr_percent
        snapshot_momentum_percent = _optional_float(
            metadata.get('snapshot_momentum_percent')
        )
        session_move_percent = _optional_float(metadata.get('session_move_percent'))
        directional_snapshot_momentum_percent = _directional_value(
            side,
            snapshot_momentum_percent,
        )
        directional_session_move_percent = _directional_value(
            side,
            session_move_percent,
        )
        tp_to_atr_ratio = _ratio(effective_take_profit_percent, atr_percent)
        tp_to_snapshot_momentum_ratio = _ratio(
            effective_take_profit_percent,
            _positive_float(directional_snapshot_momentum_percent),
        )
        required_net_move_percent = (
            evaluated_candidate.economics.estimated_total_cost_percent
            + evaluated_candidate.economics.min_expected_net_profit_percent
            + config.feasibility_buffer_percent
        )
        cost_to_tp_ratio = (
            evaluated_candidate.economics.cost_to_tp_ratio
            or _safe_ratio(
                evaluated_candidate.economics.estimated_total_cost_percent,
                effective_take_profit_percent,
            )
        )
        reward_to_risk_ratio = (
            evaluated_candidate.economics.reward_to_risk_ratio
            or _safe_ratio(
                effective_take_profit_percent,
                effective_stop_loss_percent,
            )
        )
        net_reward_to_risk_ratio = (
            evaluated_candidate.economics.net_reward_to_risk_ratio
            or _safe_ratio(
                evaluated_candidate.economics.expected_net_profit_percent,
                effective_stop_loss_percent
                + evaluated_candidate.economics.estimated_total_cost_percent,
            )
        )
        distance_to_trade_extreme_percent = _distance_to_trade_extreme(candidate)
        movement_consumed_percent = (
            max(directional_session_move_percent, 0.0)
            if directional_session_move_percent is not None
            else None
        )

        penalty = 0.0
        hard_rejection_reason: str | None = None
        components: list[str] = []
        penalty_components: list[str] = []
        hard_rejection_components: list[str] = []

        penalty = self._apply_atr_rules(
            tp_to_atr_ratio=tp_to_atr_ratio,
            penalty=penalty,
            components=components,
            penalty_components=penalty_components,
            config=config,
        )
        penalty = self._apply_momentum_rules(
            directional_snapshot_momentum_percent=(
                directional_snapshot_momentum_percent
            ),
            tp_to_snapshot_momentum_ratio=tp_to_snapshot_momentum_ratio,
            penalty=penalty,
            components=components,
            penalty_components=penalty_components,
            config=config,
        )
        penalty, hard_rejection_reason = self._apply_cost_rules(
            cost_to_tp_ratio=cost_to_tp_ratio,
            penalty=penalty,
            components=components,
            penalty_components=penalty_components,
            hard_rejection_components=hard_rejection_components,
            config=config,
        )
        penalty = self._apply_runway_rules(
            movement_consumed_percent=movement_consumed_percent,
            penalty=penalty,
            components=components,
            penalty_components=penalty_components,
            config=config,
        )

        raw_penalty = min(penalty, config.max_penalty_points)
        raw_runway_score = max(0.0, min(100.0, 100.0 - raw_penalty * 2.0))
        readiness_decision = evaluate_candidate_readiness(
            hard_rejection_reason=hard_rejection_reason,
        )
        score_before_tp_feasibility = round(candidate.score, 4)
        adjusted_score = _score_after_penalty(candidate.score, raw_penalty)

        return TpFeasibilityAnalysis(
            effective_take_profit_percent=round(effective_take_profit_percent, 4),
            effective_stop_loss_percent=round(effective_stop_loss_percent, 4),
            atr_percent=_round_optional(atr_percent),
            snapshot_momentum_percent=_round_optional(snapshot_momentum_percent),
            directional_snapshot_momentum_percent=_round_optional(
                directional_snapshot_momentum_percent
            ),
            session_move_percent=_round_optional(session_move_percent),
            directional_session_move_percent=_round_optional(
                directional_session_move_percent
            ),
            tp_to_atr_ratio=_round_optional(tp_to_atr_ratio),
            tp_to_snapshot_momentum_ratio=_round_optional(
                tp_to_snapshot_momentum_ratio
            ),
            required_net_move_percent=round(required_net_move_percent, 4),
            cost_to_tp_ratio=round(cost_to_tp_ratio, 4),
            reward_to_risk_ratio=round(reward_to_risk_ratio, 4),
            net_reward_to_risk_ratio=round(net_reward_to_risk_ratio, 4),
            sl_tp_mode=effective_sl_tp.mode,
            sl_tp_source=effective_sl_tp.source,
            distance_to_trade_extreme_percent=_round_optional(
                distance_to_trade_extreme_percent
            ),
            movement_consumed_percent=_round_optional(movement_consumed_percent),
            runway_score=round(raw_runway_score, 4),
            raw_runway_score=raw_runway_score,
            score_before_tp_feasibility=score_before_tp_feasibility,
            adjusted_score=adjusted_score,
            tp_feasibility_penalty=round(raw_penalty, 4),
            raw_tp_feasibility_penalty=raw_penalty,
            tp_feasibility_hard_rejection_reason=hard_rejection_reason,
            readiness=readiness_decision.readiness,
            readiness_reason=readiness_decision.reason,
            penalty_components=tuple(penalty_components),
            hard_rejection_components=tuple(hard_rejection_components),
            reason_components=tuple(components),
        )

    def _disabled_analysis(
        self,
        *,
        evaluated_candidate: EvaluatedTradeCandidate,
        risk_profile: RiskProfile,
    ) -> TpFeasibilityAnalysis:
        candidate = evaluated_candidate.candidate
        effective_sl_tp = (
            evaluated_candidate.effective_sl_tp
            or self.sl_tp_resolver.resolve_for_signal(
                signal=candidate.signal,
                risk_profile=risk_profile,
            )
        )
        score = round(candidate.score, 4)
        return TpFeasibilityAnalysis(
            effective_take_profit_percent=round(
                effective_sl_tp.take_profit_percent,
                4,
            ),
            effective_stop_loss_percent=round(
                effective_sl_tp.stop_loss_percent,
                4,
            ),
            atr_percent=_round_optional(effective_sl_tp.atr_percent),
            snapshot_momentum_percent=None,
            directional_snapshot_momentum_percent=None,
            session_move_percent=None,
            directional_session_move_percent=None,
            tp_to_atr_ratio=None,
            tp_to_snapshot_momentum_ratio=None,
            required_net_move_percent=0.0,
            cost_to_tp_ratio=0.0,
            reward_to_risk_ratio=(
                evaluated_candidate.economics.reward_to_risk_ratio
                or _safe_ratio(
                    effective_sl_tp.take_profit_percent,
                    effective_sl_tp.stop_loss_percent,
                )
            ),
            net_reward_to_risk_ratio=(
                evaluated_candidate.economics.net_reward_to_risk_ratio
            ),
            sl_tp_mode=effective_sl_tp.mode,
            sl_tp_source=effective_sl_tp.source,
            distance_to_trade_extreme_percent=None,
            movement_consumed_percent=None,
            runway_score=100.0,
            raw_runway_score=100.0,
            score_before_tp_feasibility=score,
            adjusted_score=score,
            tp_feasibility_penalty=0.0,
            raw_tp_feasibility_penalty=0.0,
            tp_feasibility_hard_rejection_reason=None,
            readiness=CandidateReadiness.TRADABLE_NOW,
            readiness_reason='tp_feasibility_disabled',
            penalty_components=(),
            hard_rejection_components=(),
            reason_components=('disabled',),
        )

    def _apply_atr_rules(
        self,
        *,
        tp_to_atr_ratio: float | None,
        penalty: float,
        components: list[str],
        penalty_components: list[str],
        config: TpFeasibilityConfig,
    ) -> float:
        if tp_to_atr_ratio is None:
            component = 'missing_atr'
            components.append(component)
            penalty_components.append(component)
            return penalty + config.missing_data_penalty_points
        if tp_to_atr_ratio >= config.tp_atr_severe_ratio:
            component = 'tp_too_far_vs_atr_severe'
            components.append(component)
            penalty_components.append(component)
            return penalty + 30.0
        if tp_to_atr_ratio >= config.tp_atr_hard_ratio:
            component = 'tp_too_far_vs_atr_hard'
            components.append(component)
            penalty_components.append(component)
            return penalty + 22.0
        if tp_to_atr_ratio >= config.tp_atr_soft_ratio:
            component = 'tp_too_far_vs_atr_soft'
            components.append(component)
            penalty_components.append(component)
            return penalty + _scaled_penalty(
                tp_to_atr_ratio,
                config.tp_atr_soft_ratio,
                config.tp_atr_hard_ratio,
                6.0,
                18.0,
            )
        components.append('tp_atr_ok')
        return penalty

    def _apply_momentum_rules(
        self,
        *,
        directional_snapshot_momentum_percent: float | None,
        tp_to_snapshot_momentum_ratio: float | None,
        penalty: float,
        components: list[str],
        penalty_components: list[str],
        config: TpFeasibilityConfig,
    ) -> float:
        if directional_snapshot_momentum_percent is None:
            component = 'missing_snapshot_momentum'
            components.append(component)
            penalty_components.append(component)
            return penalty + config.missing_data_penalty_points
        if directional_snapshot_momentum_percent <= 0:
            component = 'opposite_snapshot_momentum'
            components.append(component)
            penalty_components.append(component)
            return penalty + 18.0
        if (
            directional_snapshot_momentum_percent
            < config.min_directional_momentum_percent
        ):
            component = 'weak_snapshot_momentum'
            components.append(component)
            penalty_components.append(component)
            return penalty + 12.0
        if tp_to_snapshot_momentum_ratio is None:
            component = 'missing_tp_momentum_ratio'
            components.append(component)
            penalty_components.append(component)
            return penalty + config.missing_data_penalty_points
        if tp_to_snapshot_momentum_ratio >= config.tp_momentum_hard_ratio:
            component = 'tp_too_far_vs_momentum_hard'
            components.append(component)
            penalty_components.append(component)
            return penalty + 16.0
        if tp_to_snapshot_momentum_ratio >= config.tp_momentum_soft_ratio:
            component = 'tp_too_far_vs_momentum_soft'
            components.append(component)
            penalty_components.append(component)
            return penalty + _scaled_penalty(
                tp_to_snapshot_momentum_ratio,
                config.tp_momentum_soft_ratio,
                config.tp_momentum_hard_ratio,
                4.0,
                14.0,
            )
        components.append('tp_momentum_ok')
        return penalty

    def _apply_cost_rules(
        self,
        *,
        cost_to_tp_ratio: float,
        penalty: float,
        components: list[str],
        penalty_components: list[str],
        hard_rejection_components: list[str],
        config: TpFeasibilityConfig,
    ) -> tuple[float, str | None]:
        if cost_to_tp_ratio >= config.cost_to_tp_hard_reject_ratio:
            component = 'cost_to_tp_absurd_hard_reject'
            components.append(component)
            penalty_components.append(component)
            hard_rejection_components.append(component)
            return penalty + 35.0, _reason('cost_to_tp_absurd')
        if cost_to_tp_ratio >= config.cost_to_tp_severe_ratio:
            component = 'cost_to_tp_too_high_severe'
            components.append(component)
            penalty_components.append(component)
            return penalty + 35.0, None
        if cost_to_tp_ratio >= config.cost_to_tp_hard_ratio:
            component = 'cost_to_tp_too_high_hard'
            components.append(component)
            penalty_components.append(component)
            return penalty + 22.0, None
        if cost_to_tp_ratio >= config.cost_to_tp_soft_ratio:
            component = 'cost_to_tp_too_high_soft'
            components.append(component)
            penalty_components.append(component)
            return (
                penalty
                + _scaled_penalty(
                    cost_to_tp_ratio,
                    config.cost_to_tp_soft_ratio,
                    config.cost_to_tp_hard_ratio,
                    6.0,
                    18.0,
                ),
                None,
            )
        components.append('cost_to_tp_ok')
        return penalty, None

    def _apply_runway_rules(
        self,
        *,
        movement_consumed_percent: float | None,
        penalty: float,
        components: list[str],
        penalty_components: list[str],
        config: TpFeasibilityConfig,
    ) -> float:
        if movement_consumed_percent is None:
            component = 'missing_session_move'
            components.append(component)
            penalty_components.append(component)
            return penalty + config.missing_data_penalty_points
        if movement_consumed_percent >= config.late_move_hard_percent:
            component = 'movement_already_consumed_hard'
            components.append(component)
            penalty_components.append(component)
            return penalty + 16.0
        if movement_consumed_percent >= config.late_move_soft_percent:
            component = 'movement_already_consumed_soft'
            components.append(component)
            penalty_components.append(component)
            return penalty + 8.0
        components.append('runway_ok')
        return penalty


class CandidateTpFeasibilityEvaluator:
    def __init__(self, analyzer: TpFeasibilityAnalyzer | None = None):
        self.analyzer = analyzer or TpFeasibilityAnalyzer()

    def evaluate(
        self,
        *,
        evaluated_candidate: EvaluatedTradeCandidate,
        risk_profile: RiskProfile,
    ) -> EvaluatedTradeCandidate:
        analysis = self.analyzer.analyze(
            evaluated_candidate=evaluated_candidate,
            risk_profile=risk_profile,
        )
        candidate = evaluated_candidate.candidate
        updated_candidate = replace(
            candidate,
            score=analysis.adjusted_score,
            rank_reason=_append_rank_reason(candidate.rank_reason, analysis),
            tp_feasibility_metadata=analysis_to_metadata(analysis),
            tp_feasibility_penalty=analysis.tp_feasibility_penalty,
            tp_feasibility_hard_rejection_reason=(
                analysis.tp_feasibility_hard_rejection_reason
            ),
        )
        normal_evaluated_candidate = replace(
            evaluated_candidate,
            candidate=updated_candidate,
            tp_feasibility=analysis,
            readiness=analysis.readiness,
            readiness_reason=analysis.readiness_reason,
        )

        from app.execution.eu_micro_scalp_fallback import (
            EuMicroScalpFallbackAdjuster,
        )

        fallback_evaluated_candidate = EuMicroScalpFallbackAdjuster(
            self.analyzer
        ).adjust(
            raw_evaluated_candidate=evaluated_candidate,
            normal_evaluated_candidate=normal_evaluated_candidate,
            risk_profile=risk_profile,
            normal_analysis=analysis,
        )
        with_probability = self._with_tp_probability(
            fallback_evaluated_candidate
        )
        final_analysis = with_probability.tp_feasibility
        if final_analysis is None:
            return with_probability
        return replace(
            with_probability,
            readiness=final_analysis.readiness,
            readiness_reason=final_analysis.readiness_reason,
        )

    def _with_tp_probability(
        self,
        evaluated_candidate: EvaluatedTradeCandidate,
    ) -> EvaluatedTradeCandidate:
        from app.execution.scoring.tp_probability import (
            CandidateTpProbabilityEvaluator,
        )

        return CandidateTpProbabilityEvaluator().evaluate(evaluated_candidate)


def analysis_to_metadata(analysis: TpFeasibilityAnalysis) -> dict[str, Any]:
    return {
        'effective_take_profit_percent': analysis.effective_take_profit_percent,
        'effective_stop_loss_percent': analysis.effective_stop_loss_percent,
        'atr_percent': analysis.atr_percent,
        'snapshot_momentum_percent': analysis.snapshot_momentum_percent,
        'directional_snapshot_momentum_percent': (
            analysis.directional_snapshot_momentum_percent
        ),
        'session_move_percent': analysis.session_move_percent,
        'directional_session_move_percent': (
            analysis.directional_session_move_percent
        ),
        'tp_to_atr_ratio': analysis.tp_to_atr_ratio,
        'tp_to_snapshot_momentum_ratio': (
            analysis.tp_to_snapshot_momentum_ratio
        ),
        'required_net_move_percent': analysis.required_net_move_percent,
        'cost_to_tp_ratio': analysis.cost_to_tp_ratio,
        'reward_to_risk_ratio': analysis.reward_to_risk_ratio,
        'net_reward_to_risk_ratio': analysis.net_reward_to_risk_ratio,
        'sl_tp_mode': analysis.sl_tp_mode,
        'sl_tp_source': analysis.sl_tp_source,
        'distance_to_trade_extreme_percent': (
            analysis.distance_to_trade_extreme_percent
        ),
        'movement_consumed_percent': analysis.movement_consumed_percent,
        'runway_score': analysis.runway_score,
        'raw_runway_score': analysis.raw_runway_score,
        'score_before_tp_feasibility': analysis.score_before_tp_feasibility,
        'adjusted_score': analysis.adjusted_score,
        'tp_feasibility_penalty': analysis.tp_feasibility_penalty,
        'raw_tp_feasibility_penalty': analysis.raw_tp_feasibility_penalty,
        'tp_feasibility_hard_rejection_reason': (
            analysis.tp_feasibility_hard_rejection_reason
        ),
        'readiness': analysis.readiness.value,
        'readiness_reason': analysis.readiness_reason,
        'penalty_components': list(analysis.penalty_components),
        'hard_rejection_components': list(
            analysis.hard_rejection_components
        ),
        'reason_components': list(analysis.reason_components),
    }


def _append_rank_reason(
    rank_reason: str,
    analysis: TpFeasibilityAnalysis,
) -> str:
    suffix = (
        f'tp_feasibility_penalty={analysis.tp_feasibility_penalty:.2f},'
        f'runway={analysis.runway_score:.2f},'
        f'readiness={analysis.readiness.value},'
        f'readiness_reason={analysis.readiness_reason},'
        f'score_before_tp_feasibility='
        f'{analysis.score_before_tp_feasibility:.2f},'
        f'adjusted_score={analysis.adjusted_score:.2f},'
        f'sl_tp_mode={analysis.sl_tp_mode},'
        f'sl_tp_source={analysis.sl_tp_source}'
    )
    if analysis.tp_feasibility_hard_rejection_reason:
        suffix += (
            f',hard_reject='
            f'{analysis.tp_feasibility_hard_rejection_reason}'
        )
    return f'{rank_reason};{suffix}' if rank_reason else suffix


def _distance_to_trade_extreme(candidate: TradeCandidate) -> float | None:
    if candidate.signal.action == 'BUY':
        return _optional_float(
            candidate.entry_quality_metadata.get(
                'distance_to_recent_high_percent'
            )
        )
    if candidate.signal.action == 'SELL':
        return _optional_float(
            candidate.entry_quality_metadata.get(
                'distance_to_recent_low_percent'
            )
        )
    return None


def _directional_value(side: str, value: float | None) -> float | None:
    if value is None:
        return None
    if side == 'BUY':
        return value
    if side == 'SELL':
        return -value
    return None


def _ratio(numerator: float, denominator: float | None) -> float | None:
    if denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return float('inf')
    return numerator / denominator


def _positive_float(value: Any) -> float | None:
    parsed = _optional_float(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_optional(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def _scaled_penalty(
    value: float,
    soft: float,
    hard: float,
    min_penalty: float,
    max_penalty: float,
) -> float:
    if hard <= soft:
        return max_penalty
    progress = max(0.0, min(1.0, (value - soft) / (hard - soft)))
    return min_penalty + (max_penalty - min_penalty) * progress


def _score_after_penalty(score: float, penalty: float) -> float:
    return round(max(0.0, score - penalty), 4)


def _reason(reason: str) -> str:
    return f'{TP_FEASIBILITY_HARD_REJECTION_PREFIX}{reason}'
