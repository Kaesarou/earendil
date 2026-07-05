from typing import Any

from app.execution.scoring.signal_scorer import (
    directional_score_breakdown,
    float_metadata,
)
from app.execution.scoring.trade_candidate_scorer import TradeCandidateScorer
from app.execution.trade_candidate import TradeCandidate
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal
from app.utils.commons import spread_percent


_DEFAULT_TRADE_CANDIDATE_SCORER = TradeCandidateScorer()


def build_trade_candidate(
    symbol: str,
    snapshot: MarketSnapshot,
    candle: Candle,
    signal: Signal,
) -> TradeCandidate:
    score_breakdown = _score_breakdown(
        snapshot=snapshot,
        candle=candle,
        signal=signal,
    )
    score = score_breakdown.final_score
    exhaustion = score_breakdown.exhaustion
    entry_quality_metadata = _entry_quality_metadata(exhaustion)

    return TradeCandidate(
        symbol=symbol,
        snapshot=snapshot,
        candle=candle,
        signal=signal,
        score=round(score, 4),
        rank_reason=_rank_reason(
            snapshot=snapshot,
            signal=signal,
            base_score=score_breakdown.base_score,
            score=score,
            entry_quality_metadata=entry_quality_metadata,
        ),
        base_score=round(score_breakdown.base_score, 4),
        exhaustion_penalty=exhaustion.exhaustion_penalty,
        late_entry_risk=exhaustion.late_entry_risk,
        entry_quality_metadata=entry_quality_metadata,
    )


def rank_trade_candidates(candidates: list[TradeCandidate]) -> list[TradeCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: candidate.score,
        reverse=True,
    )


def _score_breakdown(
    *,
    snapshot: MarketSnapshot,
    candle: Candle,
    signal: Signal,
):
    metadata = signal.metadata or {}
    close_position_percent = float_metadata(metadata, 'close_position_percent')
    close_quality = (
        100 - close_position_percent
        if signal.action == 'SELL'
        else close_position_percent
    )
    return directional_score_breakdown(
        snapshot=snapshot,
        candle=candle,
        signal=signal,
        close_quality=close_quality,
    )


def _entry_quality_metadata(exhaustion) -> dict[str, Any]:
    return {
        'late_entry_risk': exhaustion.late_entry_risk,
        'exhaustion_penalty': exhaustion.exhaustion_penalty,
        'move_extension_percent': exhaustion.move_extension_percent,
        'extension_atr_ratio': exhaustion.extension_atr_ratio,
        'distance_to_recent_high_percent': exhaustion.distance_to_recent_high_percent,
        'distance_to_recent_low_percent': exhaustion.distance_to_recent_low_percent,
        'momentum_acceleration_percent': exhaustion.momentum_acceleration_percent,
        'momentum_deceleration_detected': exhaustion.momentum_deceleration_detected,
        'remaining_move_quality': exhaustion.remaining_move_quality,
        'reason_exhaustion_components': exhaustion.reason_exhaustion_components,
    }


def _rank_reason(
    snapshot: MarketSnapshot,
    signal: Signal,
    base_score: float,
    score: float,
    entry_quality_metadata: dict[str, Any],
) -> str:
    metadata = signal.metadata or {}

    return (
        f'score={round(score, 4)} | '
        f'base_score={round(base_score, 4)} | '
        f'exhaustion_penalty={entry_quality_metadata["exhaustion_penalty"]} | '
        f'late_entry_risk={entry_quality_metadata["late_entry_risk"]} | '
        f'remaining_move_quality={entry_quality_metadata["remaining_move_quality"]} | '
        f'exhaustion_components={entry_quality_metadata["reason_exhaustion_components"]} | '
        f'action={signal.action} | '
        f'confidence={signal.confidence} | '
        f'session_move={float_metadata(metadata, "session_move_percent")} | '
        f'trend_strength={float_metadata(metadata, "trend_strength_percent")} | '
        f'breakout={float_metadata(metadata, "breakout_percent")} | '
        f'breakdown={float_metadata(metadata, "breakdown_percent")} | '
        f'candle_range={float_metadata(metadata, "candle_range_percent")} | '
        f'close_position={float_metadata(metadata, "close_position_percent")} | '
        f'spread={round(spread_percent(snapshot), 4)}'
    )
