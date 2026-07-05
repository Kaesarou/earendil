from typing import Protocol

from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal
from app.utils.commons import spread_percent


class SignalScorer(Protocol):
    def score(
        self,
        *,
        snapshot: MarketSnapshot,
        candle: Candle,
        signal: Signal,
    ) -> float:
        ...


def directional_score(
    *,
    snapshot: MarketSnapshot,
    candle: Candle,
    signal: Signal,
    close_quality: float,
) -> float:
    metadata = signal.metadata or {}

    session_move_percent = abs(float_metadata(metadata, 'session_move_percent'))
    trend_strength_percent = abs(float_metadata(metadata, 'trend_strength_percent'))
    breakout_percent = abs(float_metadata(metadata, 'breakout_percent'))
    breakdown_percent = abs(float_metadata(metadata, 'breakdown_percent'))
    impulse_percent = max(breakout_percent, breakdown_percent)
    candle_range_percent = float_metadata(metadata, 'candle_range_percent')

    score = 0.0
    score += signal.confidence * 100
    score += min(session_move_percent * 15, 30)
    score += min(trend_strength_percent * 80, 25)
    score += min(impulse_percent * 40, 20)
    score += min(candle_range_percent * 20, 10)
    score += close_quality * 0.15
    score -= spread_percent(snapshot) * 120

    return score


def float_metadata(metadata: dict, key: str) -> float:
    value = metadata.get(key, 0.0)

    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
