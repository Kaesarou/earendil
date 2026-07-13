from datetime import datetime, timezone

from app.execution.scoring.move_exhaustion import MoveExhaustionAnalysis
from app.execution.scoring.signal_scorer import directional_score_breakdown
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal


class FlatMoveExhaustionAnalyzer:
    def analyze(self, *, candle: Candle, signal: Signal, close_quality: float) -> MoveExhaustionAnalysis:
        return MoveExhaustionAnalysis(
            late_entry_risk=0.0,
            exhaustion_penalty=0.0,
            move_extension_percent=0.0,
            extension_atr_ratio=0.0,
            distance_to_recent_high_percent=0.0,
            distance_to_recent_low_percent=0.0,
            momentum_acceleration_percent=0.0,
            momentum_deceleration_detected=False,
            remaining_move_quality='GOOD',
            reason_exhaustion_components=(),
        )


def test_signal_scorer_uses_setup_quality_bonus_without_changing_score() -> None:
    now = datetime.now(timezone.utc)
    snapshot = MarketSnapshot(
        symbol='AMD',
        bid=100.0,
        ask=100.0,
        last=100.0,
        timestamp=now,
    )
    candle = Candle(
        symbol='AMD',
        timeframe_seconds=60,
        open=99.0,
        high=101.0,
        low=98.8,
        close=100.8,
        volume=None,
        opened_at=now,
        closed_at=now,
    )
    signal = Signal(
        action='BUY',
        setup_quality=0.8,
        reason='trend_bullish_breakout',
        metadata={
            'session_move_percent': 1.0,
            'trend_strength_percent': 0.2,
            'breakout_percent': 0.3,
            'candle_range_percent': 0.4,
        },
    )

    breakdown = directional_score_breakdown(
        snapshot=snapshot,
        candle=candle,
        signal=signal,
        close_quality=90.0,
        move_exhaustion_analyzer=FlatMoveExhaustionAnalyzer(),
    )

    assert breakdown.score_metadata['setup_quality_bonus'] == 80.0
    assert breakdown.base_score == 80.0 + 15.0 + 16.0 + 12.0 + 8.0 + 13.5
