from dataclasses import dataclass
from typing import Protocol

from app.execution.scoring.move_exhaustion import (
    MoveExhaustionAnalysis,
    MoveExhaustionAnalyzer,
)
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal
from app.utils.commons import spread_percent


@dataclass(frozen=True)
class SignalScoreBreakdown:
    base_score: float
    final_score: float
    exhaustion: MoveExhaustionAnalysis


class SignalScorer(Protocol):
    def score(
        self,
        *,
        snapshot: MarketSnapshot,
        candle: Candle,
        signal: Signal,
    ) -> float:
        ...


_DEFAULT_MOVE_EXHAUSTION_ANALYZER = MoveExhaustionAnalyzer()


def directional_score(
    *,
    snapshot: MarketSnapshot,
    candle: Candle,
    signal: Signal,
    close_quality: float,
) -> float:
    return directional_score_breakdown(
        snapshot=snapshot,
        candle=candle,
        signal=signal,
        close_quality=close_quality,
    ).final_score


def directional_score_breakdown(
    *,
    snapshot: MarketSnapshot,
    candle: Candle,
    signal: Signal,
    close_quality: float,
    move_exhaustion_analyzer: MoveExhaustionAnalyzer | None = None,
) -> SignalScoreBreakdown:
    metadata = signal.metadata or {}

    session_move_percent = abs(float_metadata(metadata, 'session_move_percent'))
    trend_strength_percent = abs(float_metadata(metadata, 'trend_strength_percent'))
    breakout_percent = abs(float_metadata(metadata, 'breakout_percent'))
    breakdown_percent = abs(float_metadata(metadata, 'breakdown_percent'))
    impulse_percent = max(breakout_percent, breakdown_percent)
    candle_range_percent = float_metadata(metadata, 'candle_range_percent')

    base_score = 0.0
    base_score += signal.confidence * 100
    base_score += min(session_move_percent * 15, 30)
    base_score += min(trend_strength_percent * 80, 25)
    base_score += min(impulse_percent * 40, 20)
    base_score += min(candle_range_percent * 20, 10)
    base_score += close_quality * 0.15
    base_score -= spread_percent(snapshot) * 120

    analyzer = move_exhaustion_analyzer or _DEFAULT_MOVE_EXHAUSTION_ANALYZER
    exhaustion = analyzer.analyze(
        candle=candle,
        signal=signal,
        close_quality=close_quality,
    )

    final_score = base_score - exhaustion.exhaustion_penalty

    return SignalScoreBreakdown(
        base_score=base_score,
        final_score=final_score,
        exhaustion=exhaustion,
    )


def float_metadata(metadata: dict, key: str) -> float:
    value = metadata.get(key, 0.0)

    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
