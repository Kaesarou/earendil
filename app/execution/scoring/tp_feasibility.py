from dataclasses import dataclass, replace
from typing import Any

from app.execution.candidate_economics import EvaluatedTradeCandidate
from app.execution.trade_candidate import TradeCandidate
from app.instruments.models import RiskProfile, TpFeasibilityConfig

TP_FEASIBILITY_REJECTION_PREFIX = 'candidate_selection_tp_feasibility_'


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
    distance_to_trade_extreme_percent: float | None
    movement_consumed_percent: float | None
    runway_score: float
    tp_feasibility_penalty: float
    tp_feasibility_rejection_reason: str | None
    score_cap: float | None
    adjusted_score: float
    reason_components: tuple[str, ...]


class TpFeasibilityAnalyzer:
    def analyze(
        self,
        *,
        evaluated_candidate: EvaluatedTradeCandidate,
        risk_profile: RiskProfile,
    ) -> TpFeasibilityAnalysis:
        candidate = evaluated_candidate.candidate
        config = risk_profile.tp_feasibility
        if not config.enabled:
            return self._disabled_analysis(evaluated_candidate=evaluated_candidate, risk_profile=risk_profile)

        metadata = candidate.signal.metadata or {}
        side = candidate.signal.action
        effective_take_profit_percent = risk_profile.take_profit_percent
        effective_stop_loss_percent = risk_profile.stop_loss_percent
        atr_percent = _positive_float(metadata.get('atr_percent'))
        snapshot_momentum_percent = _optional_float(metadata.get('snapshot_momentum_percent'))
        session_move_percent = _optional_float(metadata.get('session_move_percent'))
        directional_snapshot_momentum_percent = _directional_value(side, snapshot_momentum_percent)
        directional_session_move_percent = _directional_value(side, session_move_percent)
        tp_to_atr_ratio = _ratio(effective_take_profit_percent, atr_percent)
        tp_to_snapshot_momentum_ratio = _ratio(effective_take_profit_percent, _positive_float(directional_snapshot_momentum_percent))
        required_net_move_percent = evaluated_candidate.economics.estimated_total_cost_percent + evaluated_candidate.economics.min_expected_net_profit_percent + config.feasibility_buffer_percent
        cost_to_tp_ratio = _safe_ratio(evaluated_candidate.economics.estimated_total_cost_percent, effective_take_profit_percent)
        reward_to_risk_ratio = _safe_ratio(effective_take_profit_percent, effective_stop_loss_percent)
        distance_to_trade_extreme_percent = _distance_to_trade_extreme(candidate)
        movement_consumed_percent = max(directional_session_move_percent, 0.0) if directional_session_move_percent is not None else None

        penalty = 0.0
        score_cap: float | None = None
        rejection_reason: str | None = None
        components: list[str] = []

        penalty, score_cap, rejection_reason = self._apply_atr_rules(
            tp_to_atr_ratio=tp_to_atr_ratio,
            penalty=penalty,
            score_cap=score_cap,
            rejection_reason=rejection_reason,
            components=components,
            config=config,
        )
        penalty, score_cap = self._apply_momentum_rules(
            directional_snapshot_momentum_percent=directional_snapshot_momentum_percent,
            tp_to_snapshot_momentum_ratio=tp_to_snapshot_momentum_ratio,
            penalty=penalty,
            score_cap=score_cap,
            components=components,
            config=config,
        )
        penalty, score_cap, rejection_reason = self._apply_cost_rules(
            cost_to_tp_ratio=cost_to_tp_ratio,
            penalty=penalty,
            score_cap=score_cap,
            rejection_reason=rejection_reason,
            components=components,
            config=config,
        )
        penalty, score_cap = self._apply_runway_rules(
            distance_to_trade_extreme_percent=distance_to_trade_extreme_percent,
            movement_consumed_percent=movement_consumed_percent,
            penalty=penalty,
            score_cap=score_cap,
            components=components,
            config=config,
        )
        penalty = min(round(penalty, 4), config.max_penalty_points)
        runway_score = round(max(0.0, min(100.0, 100.0 - penalty * 2.0)), 4)
        adjusted_score = _adjusted_score(candidate.score, penalty, score_cap)

        return TpFeasibilityAnalysis(
            effective_take_profit_percent=round(effective_take_profit_percent, 4),
            effective_stop_loss_percent=round(effective_stop_loss_percent, 4),
            atr_percent=_round_optional(atr_percent),
            snapshot_momentum_percent=_round_optional(snapshot_momentum_percent),
            directional_snapshot_momentum_percent=_round_optional(directional_snapshot_momentum_percent),
            session_move_percent=_round_optional(session_move_percent),
            directional_session_move_percent=_round_optional(directional_session_move_percent),
            tp_to_atr_ratio=_round_optional(tp_to_atr_ratio),
            tp_to_snapshot_momentum_ratio=_round_optional(tp_to_snapshot_momentum_ratio),
            required_net_move_percent=round(required_net_move_percent, 4),
            cost_to_tp_ratio=round(cost_to_tp_ratio, 4),
            reward_to_risk_ratio=round(reward_to_risk_ratio, 4),
            distance_to_trade_extreme_percent=_round_optional(distance_to_trade_extreme_percent),
            movement_consumed_percent=_round_optional(movement_consumed_percent),
            runway_score=runway_score,
            tp_feasibility_penalty=penalty,
            tp_feasibility_rejection_reason=rejection_reason,
            score_cap=score_cap,
            adjusted_score=adjusted_score,
            reason_components=tuple(components),
        )

    def _disabled_analysis(self, *, evaluated_candidate: EvaluatedTradeCandidate, risk_profile: RiskProfile) -> TpFeasibilityAnalysis:
        candidate = evaluated_candidate.candidate
        return TpFeasibilityAnalysis(
            effective_take_profit_percent=round(risk_profile.take_profit_percent, 4),
            effective_stop_loss_percent=round(risk_profile.stop_loss_percent, 4),
            atr_percent=None,
            snapshot_momentum_percent=None,
            directional_snapshot_momentum_percent=None,
            session_move_percent=None,
            directional_session_move_percent=None,
            tp_to_atr_ratio=None,
            tp_to_snapshot_momentum_ratio=None,
            required_net_move_percent=0.0,
            cost_to_tp_ratio=0.0,
            reward_to_risk_ratio=_safe_ratio(risk_profile.take_profit_percent, risk_profile.stop_loss_percent),
            distance_to_trade_extreme_percent=None,
            movement_consumed_percent=None,
            runway_score=100.0,
            tp_feasibility_penalty=0.0,
            tp_feasibility_rejection_reason=None,
            score_cap=None,
            adjusted_score=round(candidate.score, 4),
            reason_components=('disabled',),
        )

    def _apply_atr_rules(self, *, tp_to_atr_ratio: float | None, penalty: float, score_cap: float | None, rejection_reason: str | None, components: list[str], config: TpFeasibilityConfig) -> tuple[float, float | None, str | None]:
        if tp_to_atr_ratio is None:
            components.append('missing_atr')
            return penalty + config.missing_data_penalty_points, score_cap, rejection_reason
        if tp_to_atr_ratio >= config.tp_atr_reject_ratio:
            components.append('tp_too_far_vs_atr_reject')
            return penalty + 30.0, _min_cap(score_cap, config.severe_score_cap), _reason('tp_too_far_vs_atr')
        if tp_to_atr_ratio >= config.tp_atr_hard_ratio:
            components.append('tp_too_far_vs_atr_hard')
            return penalty + 22.0, _min_cap(score_cap, config.moderate_score_cap), rejection_reason
        if tp_to_atr_ratio >= config.tp_atr_soft_ratio:
            components.append('tp_too_far_vs_atr_soft')
            return penalty + _scaled_penalty(tp_to_atr_ratio, config.tp_atr_soft_ratio, config.tp_atr_hard_ratio, 6.0, 18.0), score_cap, rejection_reason
        components.append('tp_atr_ok')
        return penalty, score_cap, rejection_reason

    def _apply_momentum_rules(self, *, directional_snapshot_momentum_percent: float | None, tp_to_snapshot_momentum_ratio: float | None, penalty: float, score_cap: float | None, components: list[str], config: TpFeasibilityConfig) -> tuple[float, float | None]:
        if directional_snapshot_momentum_percent is None:
            components.append('missing_snapshot_momentum')
            return penalty + config.missing_data_penalty_points, score_cap
        if directional_snapshot_momentum_percent <= 0:
            components.append('opposite_snapshot_momentum')
            return penalty + 18.0, _min_cap(score_cap, config.severe_score_cap)
        if directional_snapshot_momentum_percent < config.min_directional_momentum_percent:
            components.append('weak_snapshot_momentum')
            return penalty + 12.0, _min_cap(score_cap, config.moderate_score_cap)
        if tp_to_snapshot_momentum_ratio is None:
            components.append('missing_tp_momentum_ratio')
            return penalty + config.missing_data_penalty_points, score_cap
        if tp_to_snapshot_momentum_ratio >= config.tp_momentum_hard_ratio:
            components.append('tp_too_far_vs_momentum_hard')
            return penalty + 16.0, _min_cap(score_cap, config.moderate_score_cap)
        if tp_to_snapshot_momentum_ratio >= config.tp_momentum_soft_ratio:
            components.append('tp_too_far_vs_momentum_soft')
            return penalty + _scaled_penalty(tp_to_snapshot_momentum_ratio, config.tp_momentum_soft_ratio, config.tp_momentum_hard_ratio, 4.0, 14.0), score_cap
        components.append('tp_momentum_ok')
        return penalty, score_cap

    def _apply_cost_rules(self, *, cost_to_tp_ratio: float, penalty: float, score_cap: float | None, rejection_reason: str | None, components: list[str], config: TpFeasibilityConfig) -> tuple[float, float | None, str | None]:
        if cost_to_tp_ratio >= config.cost_to_tp_reject_ratio:
            components.append('cost_to_tp_too_high_reject')
            return penalty + 35.0, _min_cap(score_cap, config.severe_score_cap), _reason('cost_to_tp_too_high')
        if cost_to_tp_ratio >= config.cost_to_tp_hard_ratio:
            components.append('cost_to_tp_too_high_hard')
            return penalty + 22.0, _min_cap(score_cap, config.moderate_score_cap), rejection_reason
        if cost_to_tp_ratio >= config.cost_to_tp_soft_ratio:
            components.append('cost_to_tp_too_high_soft')
            return penalty + _scaled_penalty(cost_to_tp_ratio, config.cost_to_tp_soft_ratio, config.cost_to_tp_hard_ratio, 6.0, 18.0), score_cap, rejection_reason
        components.append('cost_to_tp_ok')
        return penalty, score_cap, rejection_reason

    def _apply_runway_rules(self, *, distance_to_trade_extreme_percent: float | None, movement_consumed_percent: float | None, penalty: float, score_cap: float | None, components: list[str], config: TpFeasibilityConfig) -> tuple[float, float | None]:
        if distance_to_trade_extreme_percent is not None and distance_to_trade_extreme_percent <= config.near_extreme_distance_percent:
            components.append('near_recent_extreme')
            penalty += 8.0
        if movement_consumed_percent is None:
            components.append('missing_session_move')
            return penalty + config.missing_data_penalty_points, score_cap
        if movement_consumed_percent >= config.late_move_hard_percent:
            components.append('movement_already_consumed_hard')
            return penalty + 16.0, _min_cap(score_cap, config.moderate_score_cap)
        if movement_consumed_percent >= config.late_move_soft_percent:
            components.append('movement_already_consumed_soft')
            return penalty + 8.0, score_cap
        components.append('runway_ok')
        return penalty, score_cap


class CandidateTpFeasibilityEvaluator:
    def __init__(self, analyzer: TpFeasibilityAnalyzer | None = None):
        self.analyzer = analyzer or TpFeasibilityAnalyzer()

    def evaluate(self, *, evaluated_candidate: EvaluatedTradeCandidate, risk_profile: RiskProfile) -> EvaluatedTradeCandidate:
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
            tp_feasibility_score_cap=analysis.score_cap,
            tp_feasibility_rejection_reason=analysis.tp_feasibility_rejection_reason,
        )
        return replace(
            evaluated_candidate,
            candidate=updated_candidate,
            tp_feasibility=analysis,
        )


def analysis_to_metadata(analysis: TpFeasibilityAnalysis) -> dict[str, Any]:
    return {
        'effective_take_profit_percent': analysis.effective_take_profit_percent,
        'effective_stop_loss_percent': analysis.effective_stop_loss_percent,
        'atr_percent': analysis.atr_percent,
        'snapshot_momentum_percent': analysis.snapshot_momentum_percent,
        'directional_snapshot_momentum_percent': analysis.directional_snapshot_momentum_percent,
        'session_move_percent': analysis.session_move_percent,
        'directional_session_move_percent': analysis.directional_session_move_percent,
        'tp_to_atr_ratio': analysis.tp_to_atr_ratio,
        'tp_to_snapshot_momentum_ratio': analysis.tp_to_snapshot_momentum_ratio,
        'required_net_move_percent': analysis.required_net_move_percent,
        'cost_to_tp_ratio': analysis.cost_to_tp_ratio,
        'reward_to_risk_ratio': analysis.reward_to_risk_ratio,
        'distance_to_trade_extreme_percent': analysis.distance_to_trade_extreme_percent,
        'movement_consumed_percent': analysis.movement_consumed_percent,
        'runway_score': analysis.runway_score,
        'tp_feasibility_penalty': analysis.tp_feasibility_penalty,
        'tp_feasibility_rejection_reason': analysis.tp_feasibility_rejection_reason,
        'score_cap': analysis.score_cap,
        'adjusted_score': analysis.adjusted_score,
        'reason_components': list(analysis.reason_components),
    }


def _append_rank_reason(rank_reason: str, analysis: TpFeasibilityAnalysis) -> str:
    suffix = f'tp_feasibility_penalty={analysis.tp_feasibility_penalty:.2f},runway={analysis.runway_score:.2f}'
    if analysis.score_cap is not None:
        suffix += f',score_cap={analysis.score_cap:.2f}'
    if analysis.tp_feasibility_rejection_reason:
        suffix += f',reject={analysis.tp_feasibility_rejection_reason}'
    return f'{rank_reason};{suffix}' if rank_reason else suffix


def _distance_to_trade_extreme(candidate: TradeCandidate) -> float | None:
    if candidate.signal.action == 'BUY':
        return _optional_float(candidate.entry_quality_metadata.get('distance_to_recent_high_percent'))
    if candidate.signal.action == 'SELL':
        return _optional_float(candidate.entry_quality_metadata.get('distance_to_recent_low_percent'))
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


def _scaled_penalty(value: float, soft: float, hard: float, min_penalty: float, max_penalty: float) -> float:
    if hard <= soft:
        return max_penalty
    progress = max(0.0, min(1.0, (value - soft) / (hard - soft)))
    return min_penalty + (max_penalty - min_penalty) * progress


def _min_cap(current: float | None, candidate: float) -> float:
    return candidate if current is None else min(current, candidate)


def _adjusted_score(score: float, penalty: float, score_cap: float | None) -> float:
    adjusted = score - penalty
    if score_cap is not None:
        adjusted = min(adjusted, score_cap)
    return round(max(0.0, adjusted), 4)


def _reason(reason: str) -> str:
    return f'{TP_FEASIBILITY_REJECTION_PREFIX}{reason}'
