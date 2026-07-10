from typing import Any

from app.execution.scoring.sell_signal_scorer import SellSignalScorer
from app.execution.scoring.signal_scorer import (
    directional_score_breakdown,
    float_metadata,
)
from app.execution.trade_candidate import TradeCandidate
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal
from app.utils.commons import spread_percent

_DEFAULT_SELL_SCORER = SellSignalScorer()


def build_trade_candidate(
    symbol: str,
    snapshot: MarketSnapshot,
    candle: Candle,
    signal: Signal,
    session_key: str = '',
) -> TradeCandidate:
    score_breakdown = _score_breakdown(
        snapshot=snapshot,
        candle=candle,
        signal=signal,
    )
    score = score_breakdown.final_score
    exhaustion = score_breakdown.exhaustion
    entry_quality_metadata = _entry_quality_metadata(score_breakdown)
    sell_score_metadata = score_breakdown.score_metadata.get('sell_score', {})

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
            sell_score_metadata=sell_score_metadata,
        ),
        session_key=session_key,
        base_score=round(score_breakdown.base_score, 4),
        exhaustion_penalty=exhaustion.exhaustion_penalty,
        late_entry_risk=exhaustion.late_entry_risk,
        late_entry_score_cap=exhaustion.late_entry_score_cap,
        late_entry_rejection_reason=exhaustion.late_entry_rejection_reason,
        late_entry_severity=exhaustion.late_entry_severity,
        score_before_late_entry_cap=round(score_breakdown.score_before_late_entry_cap, 4),
        score_after_late_entry_cap=round(score_breakdown.score_after_late_entry_cap, 4),
        entry_quality_metadata=entry_quality_metadata,
        sell_score_metadata=sell_score_metadata,
        sell_specific_penalty=score_breakdown.sell_specific_penalty,
        sell_score_cap=score_breakdown.sell_score_cap,
        sell_rejection_reason=score_breakdown.sell_rejection_reason,
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
    if signal.action == 'SELL':
        return _DEFAULT_SELL_SCORER.score_breakdown(
            snapshot=snapshot,
            candle=candle,
            signal=signal,
        )
    return directional_score_breakdown(
        snapshot=snapshot,
        candle=candle,
        signal=signal,
        close_quality=close_quality,
    )


def _entry_quality_metadata(score_breakdown) -> dict[str, Any]:
    exhaustion = score_breakdown.exhaustion
    return {
        'setup_quality_bonus': score_breakdown.score_metadata.get('setup_quality_bonus', 0.0),
        'late_entry_risk': exhaustion.late_entry_risk,
        'exhaustion_penalty': exhaustion.exhaustion_penalty,
        'late_entry_score_cap': exhaustion.late_entry_score_cap,
        'late_entry_rejection_reason': exhaustion.late_entry_rejection_reason,
        'late_entry_severity': exhaustion.late_entry_severity,
        'score_before_late_entry_cap': round(score_breakdown.score_before_late_entry_cap, 4),
        'score_after_late_entry_cap': round(score_breakdown.score_after_late_entry_cap, 4),
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
    sell_score_metadata: dict[str, Any],
) -> str:
    metadata = signal.metadata or {}
    sell_reason = _sell_rank_reason(sell_score_metadata)

    return (
        f'score={round(score, 4)} | '
        f'base_score={round(base_score, 4)} | '
        f'setup_quality={signal.setup_quality} | '
        f'setup_quality_bonus={entry_quality_metadata["setup_quality_bonus"]} | '
        f'exhaustion_penalty={entry_quality_metadata["exhaustion_penalty"]} | '
        f'late_entry_risk={entry_quality_metadata["late_entry_risk"]} | '
        f'late_entry_severity={entry_quality_metadata["late_entry_severity"]} | '
        f'late_entry_score_cap={entry_quality_metadata["late_entry_score_cap"]} | '
        f'late_entry_rejection_reason={entry_quality_metadata["late_entry_rejection_reason"]} | '
        f'score_before_late_entry_cap={entry_quality_metadata["score_before_late_entry_cap"]} | '
        f'score_after_late_entry_cap={entry_quality_metadata["score_after_late_entry_cap"]} | '
        f'{sell_reason}'
        f'remaining_move_quality={entry_quality_metadata["remaining_move_quality"]} | '
        f'exhaustion_components={entry_quality_metadata["reason_exhaustion_components"]} | '
        f'action={signal.action} | '
        f'session_move={float_metadata(metadata, "session_move_percent")} | '
        f'trend_strength={float_metadata(metadata, "trend_strength_percent")} | '
        f'breakout={float_metadata(metadata, "breakout_percent")} | '
        f'breakdown={float_metadata(metadata, "breakdown_percent")} | '
        f'candle_range={float_metadata(metadata, "candle_range_percent")} | '
        f'close_position={float_metadata(metadata, "close_position_percent")} | '
        f'spread={round(spread_percent(snapshot), 4)}'
    )


def _sell_rank_reason(sell_score_metadata: dict[str, Any]) -> str:
    if not sell_score_metadata:
        return ''
    return (
        f'sell_specific_penalty={sell_score_metadata["sell_specific_penalty"]} | '
        f'sell_score_cap={sell_score_metadata["sell_score_cap"]} | '
        f'sell_rejection_reason={sell_score_metadata["sell_rejection_reason"]} | '
        f'sell_components={sell_score_metadata["sell_score_components"]} | '
        f'market_context_alignment={sell_score_metadata["market_context_alignment"]} | '
        f'symbol_relative_strength={sell_score_metadata["symbol_relative_strength"]} | '
        f'breakdown_strength={sell_score_metadata["breakdown_strength"]} | '
        f'short_snapshot_momentum={sell_score_metadata["short_snapshot_momentum"]} | '
        f'sell_close_quality={sell_score_metadata["sell_close_quality"]} | '
    )
