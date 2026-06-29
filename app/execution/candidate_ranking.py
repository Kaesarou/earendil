from app.execution.trade_candidate import TradeCandidate
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal
from app.utils.commons import spread_percent


def build_trade_candidate(
    symbol: str,
    snapshot: MarketSnapshot,
    candle: Candle,
    signal: Signal,
) -> TradeCandidate:
    score = _score_signal(
        snapshot=snapshot,
        candle=candle,
        signal=signal,
    )

    return TradeCandidate(
        symbol=symbol,
        snapshot=snapshot,
        candle=candle,
        signal=signal,
        score=round(score, 4),
        rank_reason=_rank_reason(
            snapshot=snapshot,
            signal=signal,
            score=score,
        ),
    )


def rank_trade_candidates(candidates: list[TradeCandidate]) -> list[TradeCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: candidate.score,
        reverse=True,
    )


def _score_signal(
    snapshot: MarketSnapshot,
    candle: Candle,
    signal: Signal,
) -> float:
    metadata = signal.metadata or {}

    session_move_percent = abs(_float_metadata(metadata, 'session_move_percent'))
    trend_strength_percent = abs(_float_metadata(metadata, 'trend_strength_percent'))
    breakout_percent = abs(_float_metadata(metadata, 'breakout_percent'))
    breakdown_percent = abs(_float_metadata(metadata, 'breakdown_percent'))
    impulse_percent = max(breakout_percent, breakdown_percent)
    candle_range_percent = _float_metadata(metadata, 'candle_range_percent')
    close_position_percent = _float_metadata(metadata, 'close_position_percent')

    if signal.action == 'SELL':
        close_quality = 100 - close_position_percent
    else:
        close_quality = close_position_percent

    score = 0.0
    score += signal.confidence * 100
    score += min(session_move_percent * 15, 30)
    score += min(trend_strength_percent * 80, 25)
    score += min(impulse_percent * 40, 20)
    score += min(candle_range_percent * 20, 10)
    score += close_quality * 0.15
    score -= spread_percent(snapshot) * 120

    return score


def _rank_reason(
    snapshot: MarketSnapshot,
    signal: Signal,
    score: float,
) -> str:
    metadata = signal.metadata or {}

    return (
        f'score={round(score, 4)} | '
        f'action={signal.action} | '
        f'confidence={signal.confidence} | '
        f'session_move={_float_metadata(metadata, "session_move_percent")} | '
        f'trend_strength={_float_metadata(metadata, "trend_strength_percent")} | '
        f'breakout={_float_metadata(metadata, "breakout_percent")} | '
        f'breakdown={_float_metadata(metadata, "breakdown_percent")} | '
        f'candle_range={_float_metadata(metadata, "candle_range_percent")} | '
        f'close_position={_float_metadata(metadata, "close_position_percent")} | '
        f'spread={round(spread_percent(snapshot), 4)}'
    )


def _float_metadata(metadata: dict, key: str) -> float:
    value = metadata.get(key, 0.0)

    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0