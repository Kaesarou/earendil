from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.execution.trade_candidate import TradeCandidate
from app.instruments.models import RiskProfile
from app.strategies.signals import Signal

SlTpMode = Literal['fixed', 'dynamic']
SlTpSource = Literal[
    'fixed',
    'missing_atr_fallback_fixed',
    'dynamic_raw',
    'dynamic_floor',
    'dynamic_cap',
    'dynamic_floor_and_cap',
    'eu_micro_scalp_fallback',
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
    def resolve(self, *, candidate: TradeCandidate, risk_profile: RiskProfile) -> EffectiveSlTp:
        return self.resolve_for_signal(signal=candidate.signal, risk_profile=risk_profile)

    def resolve_for_signal(self, *, signal: Signal, risk_profile: RiskProfile) -> EffectiveSlTp:
        atr_percent = self._atr_percent_from_signal(signal)
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
                metadata={'fallback_reason': 'missing_or_invalid_atr_percent'},
            )

        raw_sl_percent = atr_percent * risk_profile.stop_loss_atr_multiplier
        raw_tp_percent = atr_percent * risk_profile.take_profit_atr_multiplier
        sl_percent = self._clamp_percent(raw_sl_percent, risk_profile.min_stop_loss_percent, risk_profile.max_stop_loss_percent)
        tp_percent = self._clamp_percent(raw_tp_percent, risk_profile.min_take_profit_percent, risk_profile.max_take_profit_percent)
        return EffectiveSlTp(
            stop_loss_percent=sl_percent,
            take_profit_percent=tp_percent,
            atr_percent=atr_percent,
            mode='dynamic',
            source=self._dynamic_source(raw_values=(raw_sl_percent, raw_tp_percent), clamped_values=(sl_percent, tp_percent)),
            dynamic_sl_raw_percent=raw_sl_percent,
            dynamic_tp_raw_percent=raw_tp_percent,
            dynamic_sl_clamped_percent=sl_percent,
            dynamic_tp_clamped_percent=tp_percent,
            metadata={
                'stop_loss_atr_multiplier': risk_profile.stop_loss_atr_multiplier,
                'take_profit_atr_multiplier': risk_profile.take_profit_atr_multiplier,
                'min_stop_loss_percent': risk_profile.min_stop_loss_percent,
                'max_stop_loss_percent': risk_profile.max_stop_loss_percent,
                'min_take_profit_percent': risk_profile.min_take_profit_percent,
                'max_take_profit_percent': risk_profile.max_take_profit_percent,
            },
        )

    def _atr_percent_from_signal(self, signal: Signal) -> float | None:
        metadata = signal.metadata or {}
        raw_atr_percent = metadata.get('atr_percent')
        if raw_atr_percent is None:
            return None
        try:
            atr_percent = float(raw_atr_percent)
        except (TypeError, ValueError):
            return None
        return atr_percent if atr_percent > 0 else None

    def _clamp_percent(self, value: float, minimum: float, maximum: float) -> float:
        if minimum > 0:
            value = max(value, minimum)
        if maximum > 0:
            value = min(value, maximum)
        return value

    def _dynamic_source(self, *, raw_values: tuple[float, float], clamped_values: tuple[float, float]) -> SlTpSource:
        floored = any(clamped > raw for raw, clamped in zip(raw_values, clamped_values, strict=True))
        capped = any(clamped < raw for raw, clamped in zip(raw_values, clamped_values, strict=True))
        if floored and capped:
            return 'dynamic_floor_and_cap'
        if floored:
            return 'dynamic_floor'
        if capped:
            return 'dynamic_cap'
        return 'dynamic_raw'
