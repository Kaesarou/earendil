from datetime import datetime, timezone

from app.execution.candidate_ranking import build_trade_candidate
from app.execution.pre_scan import PreScanConfig, pre_scan_candidates
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal


def snapshot(symbol: str, bid: float = 99.9, ask: float = 100.1, last: float = 100.0) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        bid=bid,
        ask=ask,
        last=last,
        timestamp=datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc),
    )


def candle(symbol: str) -> Candle:
    timestamp = datetime(2026, 6, 26, 15, 30, tzinfo=timezone.utc)
    return Candle(
        symbol=symbol,
        timeframe_seconds=60,
        open=99.0,
        high=101.0,
        low=98.5,
        close=100.0,
        volume=None,
        opened_at=timestamp,
        closed_at=timestamp,
    )


def signal(
    session_move_percent: float = 1.0,
    trend_strength_percent: float = 0.3,
    atr_percent: float = 0.8,
    market_regime: str = 'TRENDING',
    noise_ratio: float = 0.4,
) -> Signal:
    return Signal(
        action='BUY',
        confidence=0.8,
        reason='test_signal',
        metadata={
            'session_move_percent': session_move_percent,
            'trend_strength_percent': trend_strength_percent,
            'breakout_percent': 0.2,
            'candle_range_percent': 0.4,
            'close_position_percent': 90.0,
            'atr_percent': atr_percent,
            'market_regime': market_regime,
            'regime_noise_ratio': noise_ratio,
        },
    )


def candidate(
    symbol: str,
    candidate_signal: Signal | None = None,
    candidate_snapshot: MarketSnapshot | None = None,
):
    return build_trade_candidate(
        symbol=symbol,
        snapshot=candidate_snapshot or snapshot(symbol),
        candle=candle(symbol),
        signal=candidate_signal or signal(),
    )


def test_pre_scan_keeps_only_top_n_candidates():
    candidates = [
        candidate('ONE', signal(session_move_percent=1.8)),
        candidate('TWO', signal(session_move_percent=1.2)),
        candidate('THREE', signal(session_move_percent=0.8)),
    ]

    result = pre_scan_candidates(
        candidates,
        PreScanConfig(top_n=2),
    )

    assert len(result.selected_candidates) == 2
    assert len(result.rejected_candidates) == 1
    assert result.rejected_candidates[0].reason == 'pre_scan_outside_top_n'




def test_pre_scan_does_not_reject_high_spread_candidate_before_risk_manager():
    high_spread = candidate(
        'WIDE',
        candidate_snapshot=snapshot('WIDE', bid=98.0, ask=102.0, last=100.0),
    )

    result = pre_scan_candidates(
        [high_spread],
        PreScanConfig(),
    )

    assert result.selected_candidates == [high_spread]
    assert result.rejected_candidates == []
