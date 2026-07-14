from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from app.execution.candidate_economics import (
    CandidateEconomics,
    EvaluatedTradeCandidate,
)
from app.execution.sl_tp_profile import EffectiveSlTp
from app.execution.trade_candidate import TradeCandidate
from app.instruments.models import AssetClass, RiskProfile
from app.risk.trade_cost_model import TradeCostModel
from app.utils.commons import spread_percent

if TYPE_CHECKING:
    from app.execution.scoring.tp_feasibility import (
        TpFeasibilityAnalysis,
        TpFeasibilityAnalyzer,
    )

logger = logging.getLogger(__name__)

FALLBACK_TP_PERCENT = 0.60
FALLBACK_SL_PERCENT = 0.60
MIN_SCORE_BEFORE_TP_FEASIBILITY = 150.0
MIN_NORMAL_ADJUSTED_SCORE = 105.0
NORMAL_EU_MIN_SCORE = 115.0
FALLBACK_SELECTION_MIN_SCORE = 110.0
MIN_EXPECTED_NET_PROFIT_PERCENT = 0.15

_REQUIRED_TP_DISTANCE_COMPONENT_PREFIXES = (
    'tp_too_far_vs_atr_',
    'tp_too_far_vs_momentum_',
)
_DISQUALIFYING_COMPONENTS = {
    'opposite_snapshot_momentum',
    'weak_snapshot_momentum',
    'missing_atr',
    'missing_snapshot_momentum',
    'missing_session_move',
    'cost_to_tp_absurd_hard_reject',
}
_DISQUALIFYING_COMPONENT_PREFIXES = (
    'movement_already_consumed_',
)


class EuMicroScalpFallbackAdjuster:
    def __init__(
        self,
        analyzer: 'TpFeasibilityAnalyzer',
        trade_cost_model: TradeCostModel | None = None,
    ):
        self.analyzer = analyzer
        self.trade_cost_model = trade_cost_model or TradeCostModel()

    def adjust(
        self,
        *,
        raw_evaluated_candidate: EvaluatedTradeCandidate,
        normal_evaluated_candidate: EvaluatedTradeCandidate,
        risk_profile: RiskProfile,
        normal_analysis: 'TpFeasibilityAnalysis',
    ) -> EvaluatedTradeCandidate:
        rejection_reason = self._eligibility_rejection_reason(
            risk_profile=risk_profile,
            normal_analysis=normal_analysis,
        )
        if rejection_reason is not None:
            logger.debug(
                'EU micro-scalp fallback skipped | symbol=%s | reason=%s',
                raw_evaluated_candidate.candidate.symbol,
                rejection_reason,
            )
            return normal_evaluated_candidate

        fallback_effective_sl_tp = self._fallback_effective_sl_tp(
            normal_analysis=normal_analysis,
            normal_evaluated_candidate=normal_evaluated_candidate,
        )
        fallback_evaluated_candidate = self._with_fallback_economics(
            source_evaluated_candidate=normal_evaluated_candidate,
            fallback_candidate=raw_evaluated_candidate.candidate,
            risk_profile=risk_profile,
            effective_sl_tp=fallback_effective_sl_tp,
        )
        fallback_analysis = self.analyzer.analyze(
            evaluated_candidate=fallback_evaluated_candidate,
            risk_profile=risk_profile,
        )
        fallback_rejection_reason = self._fallback_rejection_reason(
            fallback_evaluated_candidate,
            fallback_analysis,
        )
        if fallback_rejection_reason is not None:
            logger.info(
                'EU micro-scalp fallback rejected | symbol=%s | side=%s | '
                'reason=%s | normal_score=%s | fallback_score=%s | '
                'expected_net_percent=%s',
                raw_evaluated_candidate.candidate.symbol,
                raw_evaluated_candidate.candidate.signal.action,
                fallback_rejection_reason,
                normal_analysis.adjusted_score,
                fallback_analysis.adjusted_score,
                fallback_evaluated_candidate.economics.expected_net_profit_percent,
            )
            return normal_evaluated_candidate

        adjusted_candidate = _candidate_with_fallback_analysis(
            raw_evaluated_candidate=raw_evaluated_candidate,
            normal_analysis=normal_analysis,
            fallback_analysis=fallback_analysis,
        )
        logger.info(
            'EU micro-scalp fallback applied | symbol=%s | side=%s | '
            'old_tp=%s | old_sl=%s | new_tp=%s | new_sl=%s | '
            'normal_score=%s | fallback_score=%s | '
            'expected_net_percent=%s',
            raw_evaluated_candidate.candidate.symbol,
            raw_evaluated_candidate.candidate.signal.action,
            normal_analysis.effective_take_profit_percent,
            normal_analysis.effective_stop_loss_percent,
            FALLBACK_TP_PERCENT,
            fallback_effective_sl_tp.stop_loss_percent,
            normal_analysis.adjusted_score,
            fallback_analysis.adjusted_score,
            fallback_evaluated_candidate.economics.expected_net_profit_percent,
        )
        return replace(
            fallback_evaluated_candidate,
            candidate=adjusted_candidate,
            tp_feasibility=fallback_analysis,
        )

    def _eligibility_rejection_reason(
        self,
        *,
        risk_profile: RiskProfile,
        normal_analysis: 'TpFeasibilityAnalysis',
    ) -> str | None:
        if risk_profile.asset_class != AssetClass.EQUITY_EU:
            return 'not_equity_eu'
        if normal_analysis.tp_feasibility_hard_rejection_reason is not None:
            return 'normal_tp_feasibility_hard_reject'
        if normal_analysis.adjusted_score >= NORMAL_EU_MIN_SCORE:
            return 'normal_candidate_already_selectable'
        if normal_analysis.adjusted_score < MIN_NORMAL_ADJUSTED_SCORE:
            return 'normal_score_too_low_after_tp_feasibility'
        if (
            normal_analysis.score_before_tp_feasibility
            < MIN_SCORE_BEFORE_TP_FEASIBILITY
        ):
            return 'score_before_tp_feasibility_too_low'
        if not _has_required_tp_distance_component(
            normal_analysis.reason_components
        ):
            return 'normal_rejection_not_tp_distance_related'
        if _has_disqualifying_component(normal_analysis.reason_components):
            return 'normal_analysis_has_disqualifying_component'
        return None

    def _fallback_effective_sl_tp(
        self,
        *,
        normal_analysis: 'TpFeasibilityAnalysis',
        normal_evaluated_candidate: EvaluatedTradeCandidate,
    ) -> EffectiveSlTp:
        current = normal_evaluated_candidate.effective_sl_tp
        if current is not None and current.source == 'pending_structural':
            return EffectiveSlTp(
                stop_loss_percent=current.stop_loss_percent,
                take_profit_percent=FALLBACK_TP_PERCENT,
                atr_percent=current.atr_percent,
                mode=current.mode,
                source='pending_structural',
                dynamic_sl_raw_percent=current.dynamic_sl_raw_percent,
                dynamic_tp_raw_percent=current.dynamic_tp_raw_percent,
                dynamic_sl_clamped_percent=current.dynamic_sl_clamped_percent,
                dynamic_tp_clamped_percent=FALLBACK_TP_PERCENT,
                metadata={
                    **current.metadata,
                    'adaptation': 'eu_micro_scalp_fallback',
                    'selection_min_score': FALLBACK_SELECTION_MIN_SCORE,
                    'original_take_profit_percent': (
                        normal_analysis.effective_take_profit_percent
                    ),
                    'original_stop_loss_percent': (
                        normal_analysis.effective_stop_loss_percent
                    ),
                    'normal_adjusted_score': normal_analysis.adjusted_score,
                    'micro_scalp_take_profit_percent': FALLBACK_TP_PERCENT,
                },
            )
        return EffectiveSlTp(
            stop_loss_percent=FALLBACK_SL_PERCENT,
            take_profit_percent=FALLBACK_TP_PERCENT,
            atr_percent=normal_analysis.atr_percent,
            mode='fixed',
            source='eu_micro_scalp_fallback',
            metadata={
                'adaptation': 'eu_micro_scalp_fallback',
                'selection_min_score': FALLBACK_SELECTION_MIN_SCORE,
                'original_take_profit_percent': (
                    normal_analysis.effective_take_profit_percent
                ),
                'original_stop_loss_percent': (
                    normal_analysis.effective_stop_loss_percent
                ),
                'normal_adjusted_score': normal_analysis.adjusted_score,
                'score_before_tp_feasibility': (
                    normal_analysis.score_before_tp_feasibility
                ),
            },
        )

    def _with_fallback_economics(
        self,
        *,
        source_evaluated_candidate: EvaluatedTradeCandidate,
        fallback_candidate: TradeCandidate,
        risk_profile: RiskProfile,
        effective_sl_tp: EffectiveSlTp,
    ) -> EvaluatedTradeCandidate:
        estimate = self.trade_cost_model.estimate(
            position_value=(
                source_evaluated_candidate.economics.position_value
            ),
            expected_move_percent=effective_sl_tp.take_profit_percent,
            spread_percent=spread_percent(fallback_candidate.snapshot),
            config=risk_profile.trade_cost,
        )
        loss_at_sl_percent = (
            effective_sl_tp.stop_loss_percent
            + estimate.total_estimated_cost_percent
        )
        economics = CandidateEconomics(
            position_value=estimate.position_value,
            expected_gross_profit=estimate.expected_gross_profit,
            expected_net_profit=estimate.expected_net_profit,
            expected_net_profit_percent=estimate.expected_net_profit_percent,
            estimated_total_cost=estimate.total_estimated_cost,
            estimated_total_cost_percent=(
                estimate.total_estimated_cost_percent
            ),
            min_expected_net_profit_percent=(
                estimate.min_expected_net_profit_percent
            ),
            required_min_expected_net_profit_amount=(
                estimate.required_min_expected_net_profit_amount
            ),
            effective_take_profit_percent=(
                effective_sl_tp.take_profit_percent
            ),
            effective_stop_loss_percent=(
                effective_sl_tp.stop_loss_percent
            ),
            cost_to_tp_ratio=_safe_ratio(
                estimate.total_estimated_cost_percent,
                effective_sl_tp.take_profit_percent,
            ),
            reward_to_risk_ratio=_safe_ratio(
                effective_sl_tp.take_profit_percent,
                effective_sl_tp.stop_loss_percent,
            ),
            net_reward_to_risk_ratio=_safe_ratio(
                estimate.expected_net_profit_percent,
                loss_at_sl_percent,
            ),
        )
        return EvaluatedTradeCandidate(
            candidate=replace(
                fallback_candidate,
                score=fallback_candidate.score,
            ),
            economics=economics,
            effective_sl_tp=effective_sl_tp,
        )

    def _fallback_rejection_reason(
        self,
        evaluated_candidate: EvaluatedTradeCandidate,
        fallback_analysis: 'TpFeasibilityAnalysis',
    ) -> str | None:
        if fallback_analysis.tp_feasibility_hard_rejection_reason is not None:
            return fallback_analysis.tp_feasibility_hard_rejection_reason
        if (
            evaluated_candidate.economics.expected_net_profit_percent
            < MIN_EXPECTED_NET_PROFIT_PERCENT
        ):
            return 'fallback_expected_net_profit_too_low'
        if fallback_analysis.adjusted_score < FALLBACK_SELECTION_MIN_SCORE:
            return 'fallback_score_too_low'
        if _has_disqualifying_component(fallback_analysis.reason_components):
            return 'fallback_analysis_has_disqualifying_component'
        return None


def _candidate_with_fallback_analysis(
    *,
    raw_evaluated_candidate: EvaluatedTradeCandidate,
    normal_analysis: 'TpFeasibilityAnalysis',
    fallback_analysis: 'TpFeasibilityAnalysis',
):
    from app.execution.scoring.tp_feasibility import (
        _append_rank_reason,
        analysis_to_metadata,
    )

    candidate = raw_evaluated_candidate.candidate
    metadata = analysis_to_metadata(fallback_analysis)
    metadata.update(
        {
            'adaptation': 'eu_micro_scalp_fallback',
            'fallback_applied': True,
            'normal_effective_take_profit_percent': (
                normal_analysis.effective_take_profit_percent
            ),
            'normal_effective_stop_loss_percent': (
                normal_analysis.effective_stop_loss_percent
            ),
            'normal_adjusted_score': normal_analysis.adjusted_score,
            'fallback_selection_min_score': FALLBACK_SELECTION_MIN_SCORE,
        }
    )
    rank_reason = _append_rank_reason(
        candidate.rank_reason,
        fallback_analysis,
    )
    rank_reason = (
        f'{rank_reason};adaptation=eu_micro_scalp_fallback,'
        f'normal_adjusted_score={normal_analysis.adjusted_score:.2f}'
    )
    return replace(
        candidate,
        score=fallback_analysis.adjusted_score,
        rank_reason=rank_reason,
        tp_feasibility_metadata=metadata,
        tp_feasibility_penalty=(
            fallback_analysis.tp_feasibility_penalty
        ),
        tp_feasibility_hard_rejection_reason=(
            fallback_analysis.tp_feasibility_hard_rejection_reason
        ),
    )


def _has_required_tp_distance_component(
    components: tuple[str, ...],
) -> bool:
    return any(
        component.startswith(prefix)
        for component in components
        for prefix in _REQUIRED_TP_DISTANCE_COMPONENT_PREFIXES
    )


def _has_disqualifying_component(
    components: tuple[str, ...],
) -> bool:
    for component in components:
        if component in _DISQUALIFYING_COMPONENTS:
            return True
        if any(
            component.startswith(prefix)
            for prefix in _DISQUALIFYING_COMPONENT_PREFIXES
        ):
            return True
    return False


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator
