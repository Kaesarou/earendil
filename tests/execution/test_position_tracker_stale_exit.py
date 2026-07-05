from datetime import datetime, timedelta, timezone

from app.execution.position_tracker import PositionTracker
from app.market.models import MarketSnapshot
from app.risk.models import TradePlan


def snapshot(price: float, at: datetime) -> MarketSnapshot:
    return MarketSnapshot(symbol='AAPL', bid=price, ask=price, last=price, timestamp=at)


def trade_plan(side: str = 'BUY') -> TradePlan:
    return TradePlan(
        approved=True,
        reason='test_entry',
        symbol='AAPL',
        side=side,
        amount=1000.0,
        stop_loss=95.0 if side == 'BUY' else 105.0,
        take_profit=110.0 if side == 'BUY' else 90.0,
        estimated_total_cost_percent=0.3,
        stale_position_enabled=True,
        stale_position_max_age_minutes=60,
        stale_position_min_favorable_move_percent=0.5,
        stale_position_buffer_percent=0.1,
    )


def test_position_tracker_closes_stale_buy_position():
    opened_at = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
    tracker = PositionTracker()
    tracker.record_open_position('p1', trade_plan('BUY'), entry_price=100.0, opened_at=opened_at)

    close_signals = tracker.evaluate_snapshot(
        snapshot(100.2, opened_at + timedelta(minutes=61))
    )

    assert len(close_signals) == 1
    close_signal = close_signals[0]
    assert close_signal.reason == 'stale_position_exit'
    assert close_signal.metadata is not None
    assert close_signal.metadata['stale_position_action'] == 'CLOSE'
    assert close_signal.metadata['stale_position_age_minutes'] == 61.0
    assert close_signal.metadata['stale_position_required_mfe_percent'] == 0.5


def test_position_tracker_keeps_buy_position_with_sufficient_mfe():
    opened_at = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
    tracker = PositionTracker()
    tracker.record_open_position('p1', trade_plan('BUY'), entry_price=100.0, opened_at=opened_at)

    tracker.evaluate_snapshot(snapshot(100.6, opened_at + timedelta(minutes=30)))
    close_signals = tracker.evaluate_snapshot(
        snapshot(100.1, opened_at + timedelta(minutes=61))
    )

    assert close_signals == []


def test_position_tracker_closes_stale_sell_position():
    opened_at = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
    tracker = PositionTracker()
    tracker.record_open_position('p1', trade_plan('SELL'), entry_price=100.0, opened_at=opened_at)

    close_signals = tracker.evaluate_snapshot(
        snapshot(99.8, opened_at + timedelta(minutes=61))
    )

    assert len(close_signals) == 1
    assert close_signals[0].reason == 'stale_position_exit'


def test_position_tracker_keeps_take_profit_reason_before_stale_exit():
    opened_at = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
    tracker = PositionTracker()
    tracker.record_open_position('p1', trade_plan('BUY'), entry_price=100.0, opened_at=opened_at)

    close_signals = tracker.evaluate_snapshot(
        snapshot(110.0, opened_at + timedelta(minutes=61))
    )

    assert len(close_signals) == 1
    assert close_signals[0].reason == 'take_profit_hit'
