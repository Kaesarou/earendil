from datetime import datetime, timezone

from app.execution.scoring.sell_signal_scorer import SellSignalScorer
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal

BASE_TIME = datetime(2026, 7, 6, 15, 30, tzinfo=timezone.utc)


def snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        symbol='AMD',
        bid=99.95,
        ask=100.05,
        last=100.0,
        timestamp=BASE_TIME,
    )


def candle(close: float = 99.0, low: float = 98.9) -> Candle:
    return Candle(
        symbol='AMD',
        timeframe_seconds=60,
        open=100.5,
        high=100.8,
        low=low,
        close=close,
        volume=None,
        opened_at=BASE_TIME,
        closed_at=BASE_TIME,
    )


def sell_signal(**metadata) -> Signal:
    base_metadata = {
        'session_move_percent': -1.2,
        'trend_strength_percent': -0.25,
        'breakout_percent': 0.0,
        'breakdown_percent': 0.18,
        'candle_range_percent': 0.55,
        'close_position_percent': 8.0,
        'atr_percent': 0.5,
        'snapshot_momentum_percent': -0.40,
        'snapshot_momentum_required_percent': 0.25,
        'snapshot_breakdown_percent': 0.08,
        'snapshot_close_position_percent': 12.0,
        'regime_noise_ratio': 0.8,
    }
    base_metadata.update(metadata)
    return Signal(
        action='SELL',
        setup_quality=0.8,
        reason='test_sell',
        metadata=base_metadata,
    )


def test_sell_scorer_keeps_clean_bearish_breakdown_unpenalized():
    breakdown = SellSignalScorer().score_breakdown(
        snapshot=snapshot(),
        candle=candle(),
        signal=sell_signal(),
    )

    sell_metadata = breakdown.score_metadata['sell_score']
    assert breakdown.sell_specific_penalty == 0.0
    assert 'breakdown_ok' in sell_metadata['sell_score_components']
    assert 'short_snapshot_momentum_ok' in (
        sell_metadata['sell_score_components']
    )


def test_sell_scorer_penalizes_momentum_against_short_without_veto():
    healthy = SellSignalScorer().score_breakdown(
        snapshot=snapshot(),
        candle=candle(),
        signal=sell_signal(),
    )
    opposed = SellSignalScorer().score_breakdown(
        snapshot=snapshot(),
        candle=candle(),
        signal=sell_signal(snapshot_momentum_percent=0.05),
    )

    assert opposed.sell_specific_penalty >= 25.0
    assert opposed.final_score < healthy.final_score
    assert 'snapshot_momentum_against_short' in (
        opposed.score_metadata['sell_score']['sell_score_components']
    )


def test_sell_scorer_penalizes_weak_breakdown_without_cap():
    healthy = SellSignalScorer().score_breakdown(
        snapshot=snapshot(),
        candle=candle(),
        signal=sell_signal(),
    )
    weak = SellSignalScorer().score_breakdown(
        snapshot=snapshot(),
        candle=candle(),
        signal=sell_signal(breakdown_percent=0.02),
    )

    assert weak.sell_specific_penalty >= 14.0
    assert weak.final_score < healthy.final_score
    assert 'weak_breakdown' in (
        weak.score_metadata['sell_score']['sell_score_components']
    )


def test_sell_scorer_penalizes_snapshot_rebound_against_short():
    breakdown = SellSignalScorer().score_breakdown(
        snapshot=snapshot(),
        candle=candle(),
        signal=sell_signal(snapshot_close_position_percent=72.0),
    )

    assert breakdown.sell_specific_penalty >= 20.0
    assert 'severe_snapshot_rebound_against_short' in (
        breakdown.score_metadata['sell_score']['sell_score_components']
    )


def test_sell_scorer_penalizes_choppy_context_without_cap():
    breakdown = SellSignalScorer().score_breakdown(
        snapshot=snapshot(),
        candle=candle(),
        signal=sell_signal(regime_noise_ratio=2.2),
    )

    assert breakdown.sell_specific_penalty >= 12.0
    assert 'choppy_market_for_sell' in (
        breakdown.score_metadata['sell_score']['sell_score_components']
    )
