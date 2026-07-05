from datetime import datetime, timezone

import pytest

from app.execution.candidate_ranking import (
    build_trade_candidate,
    rank_trade_candidates,
)
from app.execution.scoring.buy_signal_scorer import BuySignalScorer
from app.execution.scoring.sell_signal_scorer import SellSignalScorer
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal
from app.utils.commons import spread_percent


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
    close_position_percent: float = 90.0,
) -> Signal:
    return Signal(
        action='BUY',
        confidence=0.8,
        reason='intraday_bullish_breakout',
        metadata={
            'session_move_percent': session_move_percent,
            'trend_strength_percent': trend_strength_percent,
            'breakout_percent': breakout_percent,
            'breakdown_percent': 0.0,
            'candle_range_percent': 0.4,
            'close_position_percent': close_position_percent,
        },
    )


def sell_signal(
    session_move_percent: float,
    trend_strength_percent: float,
    breakdown_percent: float,
    close_position_percent: float = 10.0,
) -> Signal:
    return Signal(
        action='SELL',
        confidence=0.8,
        reason='intraday_bearish_breakdown',
        metadata={
            'session_move_percent': session_move_percent,
            'trend_strength_percent': trend_strength_percent,
            'breakout_percent': 0.0,
            'breakdown_percent': breakdown_percent,
            'candle_range_percent': 0.4,
            'close_position_percent': close_position_percent,
        },
    )


def legacy_score(market_snapshot: MarketSnapshot, signal: Signal) -> float:
    metadata = signal.metadata or {}

    session_move_percent = abs(float(metadata.get('session_move_percent', 0.0) or 0.0))
    trend_strength_percent = abs(float(metadata.get('trend_strength_percent', 0.0) or 0.0))
    breakout_percent = abs(float(metadata.get('breakout_percent', 0.0) or 0.0))
    breakdown_percent = abs(float(metadata.get('breakdown_percent', 0.0) or 0.0))
    impulse_percent = max(breakout_percent, breakdown_percent)
    candle_range_percent = float(metadata.get('candle_range_percent', 0.0) or 0.0)
    close_position_percent = float(metadata.get('close_position_percent', 0.0) or 0.0)

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
    score -= spread_percent(market_snapshot) * 120

    return score


def test_buy_signal_scorer_matches_legacy_score():
    market_snapshot = snapshot('MSFT', bid=365.9, ask=366.0, last=365.95)
    closed_candle = candle('MSFT', open=362.0, high=366.0, low=361.9, close=365.95)
    signal = buy_signal(
        session_move_percent=1.8,
        trend_strength_percent=0.35,
        breakout_percent=0.25,
    )

    score = BuySignalScorer().score(
        snapshot=market_snapshot,
        candle=closed_candle,
        signal=signal,
    )

    assert score == pytest.approx(legacy_score(market_snapshot, signal))


def test_sell_signal_scorer_matches_legacy_score():
    market_snapshot = snapshot('AIR.PA', bid=190.9, ask=191.1, last=191.0)
    closed_candle = candle('AIR.PA', open=191.5, high=191.6, low=190.4, close=190.5)
    signal = sell_signal(
        session_move_percent=-1.4,
        trend_strength_percent=-0.25,
        breakdown_percent=-0.2,
        close_position_percent=12.0,
    )

    score = SellSignalScorer().score(
        snapshot=market_snapshot,
        candle=closed_candle,
        signal=signal,
    )

    assert score == pytest.approx(legacy_score(market_snapshot, signal))


def test_build_trade_candidate_scores_buy_with_buy_scorer_behavior():
    candidate = build_trade_candidate(
        symbol='MSFT',
        snapshot=snapshot('MSFT', bid=365.9, ask=366.0, last=365.95),
        candle=candle('MSFT', open=362.0, high=366.0, low=361.9, close=365.95),
        signal=buy_signal(
            session_move_percent=1.8,
            trend_strength_percent=0.35,
            breakout_percent=0.25,
            close_position_percent=90.0,
        ),
    )

    assert candidate.score == round(legacy_score(candidate.snapshot, candidate.signal), 4)


def test_build_trade_candidate_scores_sell_with_sell_scorer_behavior():
    candidate = build_trade_candidate(
        symbol='AIR.PA',
        snapshot=snapshot('AIR.PA', bid=190.9, ask=191.1, last=191.0),
        candle=candle('AIR.PA', open=191.5, high=191.6, low=190.4, close=190.5),
        signal=sell_signal(
            session_move_percent=-1.4,
            trend_strength_percent=-0.25,
            breakdown_percent=-0.2,
            close_position_percent=90.0,
        ),
    )

    assert candidate.score == round(legacy_score(candidate.snapshot, candidate.signal), 4)


def test_hold_or_unknown_action_keeps_legacy_buy_compatible_scoring():
    candidate = build_trade_candidate(
        symbol='UNKNOWN',
        snapshot=snapshot('UNKNOWN', bid=99.9, ask=100.1, last=100.0),
        candle=candle('UNKNOWN', open=99.0, high=101.0, low=98.5, close=100.0),
        signal=Signal(
            action='HOLD',
            confidence=0.0,
            reason='test_hold',
            metadata={
                'session_move_percent': 1.0,
                'trend_strength_percent': 0.2,
                'breakout_percent': 0.1,
                'breakdown_percent': 0.0,
                'candle_range_percent': 0.4,
                'close_position_percent': 75.0,
            },
        ),
    )

    assert candidate.score == round(legacy_score(candidate.snapshot, candidate.signal), 4)


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
