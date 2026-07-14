from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.execution.candidate_economics import EvaluatedTradeCandidate
from app.instruments.models import EntryDecisionConfig
from app.market.market_context import ContextAlignment, MarketRegime


ENTRY_DECISION_MODEL_VERSION = 'entry_router_v3'


class EntryAction(StrEnum):
    READY_FOR_SELECTION = 'ready_for_selection'
    WAIT_FOR_RETEST = 'wait_for_retest'
    SKIP = 'skip'


@dataclass(frozen=True)
class EntryDecision:
    action: EntryAction
    reason: str
    model_version: str = ENTRY_DECISION_MODEL_VERSION
    context_alignment: ContextAlignment = ContextAlignment.UNKNOWN
    retest_eligible: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)


class EntryDecisionEngine:
    def evaluate(
        self,
        *,
        evaluated_candidate: EvaluatedTradeCandidate,
        config: EntryDecisionConfig,
    ) -> EntryDecision:
        candidate = evaluated_candidate.candidate
        context = candidate.market_context
        alignment = context.alignment if context is not None else ContextAlignment.UNKNOWN
        feasibility = evaluated_candidate.tp_feasibility
        economics = evaluated_candidate.economics
        hard_rejection = (
            candidate.late_entry_rejection_reason
            or candidate.sell_rejection_reason
            or getattr(feasibility, 'tp_feasibility_hard_rejection_reason', None)
            or candidate.tp_feasibility_hard_rejection_reason
        )
        diagnostics = self._diagnostics(evaluated_candidate)

        if economics.expected_net_profit_percent < economics.min_expected_net_profit_percent:
            return self._decision(
                EntryAction.SKIP,
                'candidate_selection_expected_profit_too_low_after_fees',
                alignment,
                False,
                diagnostics,
            )
        if hard_rejection is not None:
            return self._decision(
                EntryAction.SKIP,
                str(hard_rejection),
                alignment,
                False,
                diagnostics,
            )
        if alignment == ContextAlignment.OPPOSED and config.context_opposition_is_hard_reject:
            return self._decision(
                EntryAction.SKIP,
                'market_context_opposed',
                alignment,
                False,
                diagnostics,
            )
        if (
            config.require_context
            and (context is None or context.regime == MarketRegime.UNKNOWN)
        ):
            return self._decision(
                EntryAction.SKIP,
                'market_context_unavailable',
                alignment,
                False,
                diagnostics,
            )

        extension_percent, retest_level = _extension_from_reference(candidate)
        structural_retest_score = _structural_retest_score(candidate)
        feasibility_runway_score = _runway_score(feasibility)
        retest_eligible = (
            retest_level is not None
            and extension_percent is not None
            and extension_percent >= config.moderate_extension_percent
            and structural_retest_score >= config.minimum_retest_runway_score
        )
        diagnostics.update(
            {
                'extension_percent': _round_optional(extension_percent),
                'retest_level': _round_optional(retest_level),
                'runway_score': _round_optional(structural_retest_score),
                'structural_retest_score': _round_optional(structural_retest_score),
                'feasibility_runway_score': _round_optional(feasibility_runway_score),
                'feasibility_penalty': _round_optional(_feasibility_penalty(feasibility)),
            }
        )

        if extension_percent is not None and extension_percent >= config.severe_extension_percent:
            return self._decision(
                EntryAction.SKIP,
                'price_too_extended_for_entry',
                alignment,
                False,
                diagnostics,
            )

        feasibility_penalty = _feasibility_penalty(feasibility)
        if feasibility_penalty >= config.severe_feasibility_penalty and not retest_eligible:
            return self._decision(
                EntryAction.SKIP,
                'severe_feasibility_penalty_without_useful_retest',
                alignment,
                False,
                diagnostics,
            )

        needs_retest = (
            retest_eligible
            and (
                extension_percent is not None
                and extension_percent >= config.moderate_extension_percent
                or feasibility_penalty >= config.wait_for_retest_penalty
                or alignment == ContextAlignment.NEUTRAL
            )
        )
        if needs_retest:
            return self._decision(
                EntryAction.WAIT_FOR_RETEST,
                'better_entry_required_at_structure',
                alignment,
                True,
                diagnostics,
            )

        if alignment == ContextAlignment.UNKNOWN and config.require_context:
            return self._decision(
                EntryAction.SKIP,
                'market_context_unknown',
                alignment,
                False,
                diagnostics,
            )

        return self._decision(
            EntryAction.READY_FOR_SELECTION,
            'entry_conditions_satisfied',
            alignment,
            False,
            diagnostics,
        )

    def _diagnostics(
        self,
        evaluated_candidate: EvaluatedTradeCandidate,
    ) -> dict[str, Any]:
        candidate = evaluated_candidate.candidate
        context = candidate.market_context
        return {
            'candidate_id': candidate.candidate_id,
            'score': candidate.score,
            'side': candidate.signal.action,
            'market_regime': context.regime.value if context is not None else None,
            'context_reasons': list(context.reasons) if context is not None else [],
            'expected_net_profit_percent': (
                evaluated_candidate.economics.expected_net_profit_percent
            ),
            'minimum_expected_net_profit_percent': (
                evaluated_candidate.economics.min_expected_net_profit_percent
            ),
        }

    def _decision(
        self,
        action: EntryAction,
        reason: str,
        alignment: ContextAlignment,
        retest_eligible: bool,
        diagnostics: dict[str, Any],
    ) -> EntryDecision:
        return EntryDecision(
            action=action,
            reason=reason,
            context_alignment=alignment,
            retest_eligible=retest_eligible,
            diagnostics=diagnostics,
        )


def _extension_from_reference(candidate) -> tuple[float | None, float | None]:
    metadata = candidate.signal.metadata or {}
    side = candidate.signal.action.strip().upper()
    key = 'range_high' if side == 'BUY' else 'range_low'
    try:
        level = float(metadata.get(key))
    except (TypeError, ValueError):
        return None, None
    if level <= 0:
        return None, None
    current = candidate.snapshot.last
    if side == 'BUY':
        extension = ((current - level) / level) * 100
    elif side == 'SELL':
        extension = ((level - current) / level) * 100
    else:
        return None, level
    return max(0.0, extension), level


def _structural_retest_score(candidate) -> float:
    quality = str(
        candidate.entry_quality_metadata.get('remaining_move_quality', 'GOOD')
    ).strip().upper()
    return {
        'GOOD': 100.0,
        'ACCEPTABLE': 50.0,
        'POOR': 0.0,
    }.get(quality, 0.0)


def _runway_score(feasibility: Any) -> float:
    if feasibility is None:
        return 100.0
    value = getattr(feasibility, 'raw_runway_score', None)
    if value is None:
        value = getattr(feasibility, 'runway_score', 100.0)
    return float(value)


def _feasibility_penalty(feasibility: Any) -> float:
    if feasibility is None:
        return 0.0
    value = getattr(feasibility, 'raw_tp_feasibility_penalty', None)
    if value is None:
        value = getattr(feasibility, 'tp_feasibility_penalty', 0.0)
    return float(value)


def _round_optional(value: float | None) -> float | None:
    return None if value is None else round(value, 4)
