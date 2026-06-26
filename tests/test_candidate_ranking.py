from datetime import datetime, timezone

from app.execution.candidate_ranking import (
    build_trade_candidate,
    rank_trade_candidates,
)
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal


def snapshot(symbol: str, bid: float, ask: float, last: float) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        bid=bid,
        ask=ask,
        last=last,
        timestamp=datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc),
    )


def candle(symbol: str, open: float, high: float, low: float, close: float) -> Candle:
    opened_at = datetime(2026, 6, 26, 15, 29, tzinfo=timezone.utc)
    closed_at = datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc)

    return Candle(
        symbol=symbol,
        timeframe_seconds=60,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=None,
        opened_at=opened_at,
        closed_at=closed_at,
    )


def buy_signal(
    session_move_percent: float,
    trend_strength_percent: float,
    breakout_percent: float,
) -> Signal:
    return Signal(
        action='BUY',
        confidence=0.8,
        reason='intraday_bullish_breakout',
        metadata={
            'session_move_percent': session_move_percent,
            'trend_strength_percent': trend_strength_percent,
            'breakout_percent': breakout_percent,
            'candle_range_percent': 0.4,
            'close_position_percent': 90.0,
        },
    )


def test_candidate_ranking_puts_stronger_opportunity_first():
    weaker = build_trade_candidate(
        symbol='AIR.PA',
        snapshot=snapshot('AIR.PA', bid=190.9, ask=191.1, last=191.0),
        candle=candle('AIR.PA', open=190.5, high=191.1, low=190.4, close=191.0),
        signal=buy_signal(
            session_move_percent=0.25,
            trend_strength_percent=0.05,
            breakout_percent=0.05,
        ),
    )

    stronger = build_trade_candidate(
        symbol='MSFT',
        snapshot=snapshot('MSFT', bid=365.9, ask=366.0, last=365.95),
        candle=candle('MSFT', open=362.0, high=366.0, low=361.9, close=365.95),
        signal=buy_signal(
            session_move_percent=1.8,
            trend_strength_percent=0.35,
            breakout_percent=0.25,
        ),
    )

    ranked = rank_trade_candidates([weaker, stronger])

    assert ranked[0].symbol == 'MSFT'
    assert ranked[1].symbol == 'AIR.PA'
    assert ranked[0].score > ranked[1].score


def test_candidate_ranking_penalizes_wide_spread():
    tight_spread = build_trade_candidate(
        symbol='MSFT',
        snapshot=snapshot('MSFT', bid=365.9, ask=366.0, last=365.95),
        candle=candle('MSFT', open=362.0, high=366.0, low=361.9, close=365.95),
        signal=buy_signal(
            session_move_percent=1.0,
            trend_strength_percent=0.2,
            breakout_percent=0.2,
        ),
    )

    wide_spread = build_trade_candidate(
        symbol='WIDE',
        snapshot=snapshot('WIDE', bid=360.0, ask=370.0, last=365.0),
        candle=candle('WIDE', open=362.0, high=366.0, low=361.9, close=365.95),
        signal=buy_signal(
            session_move_percent=1.0,
            trend_strength_percent=0.2,
            breakout_percent=0.2,
        ),
    )

    assert tight_spread.score > wide_spread.score