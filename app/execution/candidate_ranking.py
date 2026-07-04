from app.execution.scoring.signal_scorer import float_metadata
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
    score = _DEFAULT_TRADE_CANDIDATE_SCORER.score(
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
        f'session_move={float_metadata(metadata, "session_move_percent")} | '
        f'trend_strength={float_metadata(metadata, "trend_strength_percent")} | '
        f'breakout={float_metadata(metadata, "breakout_percent")} | '
        f'breakdown={float_metadata(metadata, "breakdown_percent")} | '
        f'candle_range={float_metadata(metadata, "candle_range_percent")} | '
        f'close_position={float_metadata(metadata, "close_position_percent")} | '
        f'spread={round(spread_percent(snapshot), 4)}'
    )
