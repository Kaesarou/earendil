from dataclasses import dataclass

from app.execution.scoring.signal_scorer import SignalScoreBreakdown, directional_score_breakdown, float_metadata
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal

SELL_REJECTION_PREFIX = 'candidate_selection_sell_'


@dataclass(frozen=True)
class SellScoreConfig:
    min_breakdown_percent: float = 0.08
    min_snapshot_breakdown_percent: float = 0.04
    snapshot_momentum_multiplier: float = 1.25
    default_required_short_snapshot_momentum_percent: float = 0.25
    weak_close_quality_percent: float = 80.0
    severe_close_quality_percent: float = 65.0
    max_noise_ratio: float = 1.70
    max_snapshot_close_position_percent: float = 40.0
    severe_snapshot_close_position_percent: float = 65.0
    moderate_score_cap: float = 105.0
    severe_score_cap: float = 95.0


@dataclass(frozen=True)
class SellScoreAnalysis:
    breakdown_strength: float
    short_snapshot_momentum: float
    required_short_snapshot_momentum: float
    sell_close_quality: float
    snapshot_breakdown_strength: float
    snapshot_close_position_percent: float
    regime_noise_ratio: float
    market_context_alignment: str
    symbol_relative_strength: float | None
    sell_specific_penalty: float
    sell_score_cap: float | None
    sell_rejection_reason: str | None
    reason_components: tuple[str, ...]


class SellSignalScorer:
    def __init__(self, config: SellScoreConfig | None = None):
        self.config = config or SellScoreConfig()

    def score(
        self,
        *,
        snapshot: MarketSnapshot,
        candle: Candle,
        signal: Signal,
    ) -> float:
        return self.score_breakdown(snapshot=snapshot, candle=candle, signal=signal).final_score

    def score_breakdown(
        self,
        *,
        snapshot: MarketSnapshot,
        candle: Candle,
        signal: Signal,
    ) -> SignalScoreBreakdown:
        metadata = signal.metadata or {}
        close_position_percent = float_metadata(metadata, 'close_position_percent')
        close_quality = 100 - close_position_percent
        base_breakdown = directional_score_breakdown(
            snapshot=snapshot,
            candle=candle,
            signal=signal,
            close_quality=close_quality,
        )
        analysis = self._analyze(metadata=metadata, sell_close_quality=close_quality)
        final_score = self._apply_sell_adjustments(
            score=base_breakdown.final_score,
            penalty=analysis.sell_specific_penalty,
            score_cap=analysis.sell_score_cap,
        )
        return SignalScoreBreakdown(
            base_score=base_breakdown.base_score,
            final_score=final_score,
            exhaustion=base_breakdown.exhaustion,
            score_before_late_entry_cap=base_breakdown.score_before_late_entry_cap,
            score_after_late_entry_cap=base_breakdown.score_after_late_entry_cap,
            score_metadata={
                **base_breakdown.score_metadata,
                'sell_score': self._metadata(analysis, final_score),
            },
            sell_specific_penalty=analysis.sell_specific_penalty,
            sell_score_cap=analysis.sell_score_cap,
            sell_rejection_reason=analysis.sell_rejection_reason,
        )

    def _analyze(self, *, metadata: dict, sell_close_quality: float) -> SellScoreAnalysis:
        breakdown_strength = abs(float_metadata(metadata, 'breakdown_percent'))
        snapshot_momentum = float_metadata(metadata, 'snapshot_momentum_percent')
        short_snapshot_momentum = -snapshot_momentum
        snapshot_breakdown_strength = abs(float_metadata(metadata, 'snapshot_breakdown_percent'))
        snapshot_close_position_percent = float_metadata(metadata, 'snapshot_close_position_percent')
        regime_noise_ratio = float_metadata(metadata, 'regime_noise_ratio')
        required_short_snapshot_momentum = self._required_short_snapshot_momentum(metadata)
        penalty = 0.0
        score_cap: float | None = None
        rejection_reason: str | None = None
        components: list[str] = []

        if breakdown_strength <= 0:
            components.append('false_breakdown')
            rejection_reason = self._reason('false_breakdown')
            penalty += 25.0
            score_cap = self._min_cap(score_cap, self.config.severe_score_cap)
        elif breakdown_strength < self.config.min_breakdown_percent:
            components.append('weak_breakdown')
            penalty += 14.0
            score_cap = self._min_cap(score_cap, self.config.moderate_score_cap)
        else:
            components.append('breakdown_ok')

        if short_snapshot_momentum <= 0:
            components.append('snapshot_momentum_against_short')
            rejection_reason = rejection_reason or self._reason('momentum_against_short')
            penalty += 25.0
            score_cap = self._min_cap(score_cap, self.config.severe_score_cap)
        elif short_snapshot_momentum < required_short_snapshot_momentum:
            components.append('weak_short_snapshot_momentum')
            penalty += 18.0
            score_cap = self._min_cap(score_cap, self.config.severe_score_cap)
        else:
            components.append('short_snapshot_momentum_ok')

        if sell_close_quality < self.config.severe_close_quality_percent:
            components.append('severe_weak_sell_close_quality')
            penalty += 18.0
            score_cap = self._min_cap(score_cap, self.config.severe_score_cap)
        elif sell_close_quality < self.config.weak_close_quality_percent:
            components.append('weak_sell_close_quality')
            penalty += 8.0
            score_cap = self._min_cap(score_cap, self.config.moderate_score_cap)
        else:
            components.append('sell_close_quality_ok')

        if regime_noise_ratio > self.config.max_noise_ratio:
            components.append('choppy_market_for_sell')
            penalty += 12.0
            score_cap = self._min_cap(score_cap, self.config.moderate_score_cap)

        if snapshot_breakdown_strength and snapshot_breakdown_strength < self.config.min_snapshot_breakdown_percent:
            components.append('weak_snapshot_breakdown')
            penalty += 10.0
            score_cap = self._min_cap(score_cap, self.config.moderate_score_cap)

        if snapshot_close_position_percent >= self.config.severe_snapshot_close_position_percent:
            components.append('severe_snapshot_rebound_against_short')
            penalty += 20.0
            score_cap = self._min_cap(score_cap, self.config.severe_score_cap)
        elif snapshot_close_position_percent >= self.config.max_snapshot_close_position_percent:
            components.append('snapshot_rebound_against_short')
            penalty += 12.0
            score_cap = self._min_cap(score_cap, self.config.moderate_score_cap)

        return SellScoreAnalysis(
            breakdown_strength=round(breakdown_strength, 4),
            short_snapshot_momentum=round(short_snapshot_momentum, 4),
            required_short_snapshot_momentum=round(required_short_snapshot_momentum, 4),
            sell_close_quality=round(sell_close_quality, 4),
            snapshot_breakdown_strength=round(snapshot_breakdown_strength, 4),
            snapshot_close_position_percent=round(snapshot_close_position_percent, 4),
            regime_noise_ratio=round(regime_noise_ratio, 4),
            market_context_alignment='not_available_v1',
            symbol_relative_strength=None,
            sell_specific_penalty=round(penalty, 4),
            sell_score_cap=score_cap,
            sell_rejection_reason=rejection_reason,
            reason_components=tuple(components),
        )

    def _required_short_snapshot_momentum(self, metadata: dict) -> float:
        configured = float_metadata(metadata, 'snapshot_momentum_required_percent')
        if configured <= 0:
            return self.config.default_required_short_snapshot_momentum_percent
        return configured * self.config.snapshot_momentum_multiplier

    def _apply_sell_adjustments(self, *, score: float, penalty: float, score_cap: float | None) -> float:
        adjusted = score - penalty
        if score_cap is not None:
            adjusted = min(adjusted, score_cap)
        return round(max(adjusted, 0.0), 4)

    def _metadata(self, analysis: SellScoreAnalysis, final_score: float) -> dict:
        return {
            'sell_score_components': list(analysis.reason_components),
            'market_context_alignment': analysis.market_context_alignment,
            'symbol_relative_strength': analysis.symbol_relative_strength,
            'breakdown_strength': analysis.breakdown_strength,
            'short_snapshot_momentum': analysis.short_snapshot_momentum,
            'required_short_snapshot_momentum': analysis.required_short_snapshot_momentum,
            'sell_close_quality': analysis.sell_close_quality,
            'snapshot_breakdown_strength': analysis.snapshot_breakdown_strength,
            'snapshot_close_position_percent': analysis.snapshot_close_position_percent,
            'regime_noise_ratio': analysis.regime_noise_ratio,
            'sell_specific_penalty': analysis.sell_specific_penalty,
            'sell_score_cap': analysis.sell_score_cap,
            'sell_rejection_reason': analysis.sell_rejection_reason,
            'final_sell_score': final_score,
        }

    def _reason(self, reason: str) -> str:
        return f'{SELL_REJECTION_PREFIX}{reason}'

    def _min_cap(self, current: float | None, candidate: float) -> float:
        return candidate if current is None else min(current, candidate)
