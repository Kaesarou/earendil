from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.execution.trade_candidate import TradeCandidate
from app.instruments.models import RiskProfile
from app.risk.structural_stop import calculate_structural_stop
from app.strategies.signals import Signal
from app.utils.commons import spread_percent


SlTpMode = Literal['fixed', 'dynamic']
SlTpSource = Literal[
    'fixed',
    'missing_atr_fallback_fixed',
    'dynamic_raw',
    'dynamic_floor',
    'dynamic_cap',
    'dynamic_floor_and_cap',
    'eu_trend_buy_v1',
    'pending_structural',
]


@dataclass(frozen=True)
class EffectiveSlTp:
    stop_loss_percent: float
    take_profit_percent: float
    atr_percent: float | None
    mode: SlTpMode
    source: SlTpSource
    dynamic_sl_raw_percent: float | None = None
    dynamic_tp_raw_percent: float | None = None
    dynamic_sl_clamped_percent: float | None = None
    dynamic_tp_clamped_percent: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def dynamic_sl_tp_enabled(self) -> bool:
        return self.mode == 'dynamic'


class EffectiveSlTpResolver:
    def resolve(
        self,
        *,
        candidate: TradeCandidate,
        risk_profile: RiskProfile,
    ) -> EffectiveSlTp:
        baseline = self.resolve_for_signal(
            signal=candidate.signal,
            risk_profile=risk_profile,
        )
        metadata = candidate.signal.metadata or {}
        if metadata.get('entry_origin') != 'pending_confirmation':
            return baseline

        raw_invalidation = metadata.get('structural_invalidation_price')
        try:
            invalidation_price = (
                float(raw_invalidation)
                if raw_invalidation is not None
                else None
            )
        except (TypeError, ValueError):
            invalidation_price = None
        structural = calculate_structural_stop(
            side=candidate.signal.action,
            entry_price=candidate.snapshot.last,
            invalidation_price=invalidation_price,
            atr_percent=baseline.atr_percent,
            atr_multiplier=risk_profile.stop_loss_atr_multiplier,
            minimum_distance_percent=risk_profile.min_stop_loss_percent,
            spread_percent=spread_percent(candidate.snapshot),
        )
        structural_metadata = {
            **baseline.metadata,
            'entry_origin': 'pending_confirmation',
            'structural_confirmation_satisfied': True,
            'structural_stop_valid': structural.valid,
            'structural_stop_reason': structural.reason,
            'structural_invalidation_price': structural.invalidation_price,
            'structural_distance_percent': (
                structural.structural_distance_percent
            ),
            'volatility_distance_percent': (
                structural.volatility_distance_percent
            ),
            'minimum_distance_percent': structural.minimum_distance_percent,
            'constant_risk_baseline_stop_loss_percent': (
                baseline.stop_loss_percent
            ),
            'baseline_sl_tp_source': baseline.source,
        }
        return EffectiveSlTp(
            stop_loss_percent=(
                structural.effective_distance_percent
                if structural.valid
                else baseline.stop_loss_percent
            ),
            take_profit_percent=baseline.take_profit_percent,
            atr_percent=baseline.atr_percent,
            mode=baseline.mode,
            source='pending_structural',
            dynamic_sl_raw_percent=baseline.dynamic_sl_raw_percent,
            dynamic_tp_raw_percent=baseline.dynamic_tp_raw_percent,
            dynamic_sl_clamped_percent=baseline.dynamic_sl_clamped_percent,
            dynamic_tp_clamped_percent=baseline.dynamic_tp_clamped_percent,
            metadata=structural_metadata,
        )

    def resolve_for_signal(
        self,
        *,
        signal: Signal,
        risk_profile: RiskProfile,
    ) -> EffectiveSlTp:
        atr_percent = self._atr_percent_from_signal(signal)
        directional_override = risk_profile.directional_override_for(
            signal.action
        )
        if directional_override is not None:
            return EffectiveSlTp(
                stop_loss_percent=directional_override.stop_loss_percent,
                take_profit_percent=directional_override.take_profit_percent,
                atr_percent=atr_percent,
                mode='fixed',
                source=directional_override.source,
                metadata={
                    'directional_profile': directional_override.source,
                    'side': signal.action,
                },
            )
        if not risk_profile.dynamic_sl_tp_enabled:
            return EffectiveSlTp(
                stop_loss_percent=risk_profile.stop_loss_percent,
                take_profit_percent=risk_profile.take_profit_percent,
                atr_percent=atr_percent,
                mode='fixed',
                source='fixed',
            )
        if atr_percent is None:
            return EffectiveSlTp(
                stop_loss_percent=risk_profile.stop_loss_percent,
                take_profit_percent=risk_profile.take_profit_percent,
                atr_percent=None,
                mode='fixed',
                source='missing_atr_fallback_fixed',
                metadata={
                    'fallback_reason': 'missing_or_invalid_atr_percent'
                },
            )

        raw_sl_percent = (
            atr_percent * risk_profile.stop_loss_atr_multiplier
        )
        raw_tp_percent = (
            atr_percent * risk_profile.take_profit_atr_multiplier
        )
        sl_percent = self._clamp_percent(
            raw_sl_percent,
            risk_profile.min_stop_loss_percent,
            risk_profile.max_stop_loss_percent,
        )
        tp_percent = self._clamp_percent(
            raw_tp_percent,
            risk_profile.min_take_profit_percent,
            risk_profile.max_take_profit_percent,
        )
        return EffectiveSlTp(
            stop_loss_percent=sl_percent,
            take_profit_percent=tp_percent,
            atr_percent=atr_percent,
            mode='dynamic',
            source=self._dynamic_source(
                raw_values=(raw_sl_percent, raw_tp_percent),
                clamped_values=(sl_percent, tp_percent),
            ),
            dynamic_sl_raw_percent=raw_sl_percent,
            dynamic_tp_raw_percent=raw_tp_percent,
            dynamic_sl_clamped_percent=sl_percent,
            dynamic_tp_clamped_percent=tp_percent,
            metadata={
                'stop_loss_atr_multiplier': (
                    risk_profile.stop_loss_atr_multiplier
                ),
                'take_profit_atr_multiplier': (
                    risk_profile.take_profit_atr_multiplier
                ),
                'min_stop_loss_percent': risk_profile.min_stop_loss_percent,
                'max_stop_loss_percent': risk_profile.max_stop_loss_percent,
                'min_take_profit_percent': (
                    risk_profile.min_take_profit_percent
                ),
                'max_take_profit_percent': (
                    risk_profile.max_take_profit_percent
                ),
            },
        )

    def _atr_percent_from_signal(self, signal: Signal) -> float | None:
        raw_atr_percent = (signal.metadata or {}).get('atr_percent')
        if raw_atr_percent is None:
            return None
        try:
            atr_percent = float(raw_atr_percent)
        except (TypeError, ValueError):
            return None
        return atr_percent if atr_percent > 0 else None

    def _clamp_percent(
        self,
        value: float,
        minimum: float,
        maximum: float,
    ) -> float:
        if minimum > 0:
            value = max(value, minimum)
        if maximum > 0:
            value = min(value, maximum)
        return value

    def _dynamic_source(
        self,
        *,
        raw_values: tuple[float, float],
        clamped_values: tuple[float, float],
    ) -> SlTpSource:
        floored = any(
            clamped > raw
            for raw, clamped in zip(
                raw_values,
                clamped_values,
                strict=True,
            )
        )
        capped = any(
            clamped < raw
            for raw, clamped in zip(
                raw_values,
                clamped_values,
                strict=True,
            )
        )
        if floored and capped:
            return 'dynamic_floor_and_cap'
        if floored:
            return 'dynamic_floor'
        if capped:
            return 'dynamic_cap'
        return 'dynamic_raw'
