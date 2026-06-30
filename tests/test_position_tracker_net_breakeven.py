from datetime import datetime, timezone

from app.execution.position_tracker import PositionTracker, TrackedPosition
from app.market.models import MarketSnapshot


def tracked_position(
    *,
    side: str,
    breakeven_trigger_percent: float,
    breakeven_buffer_percent: float,
) -> TrackedPosition:
    return TrackedPosition(
        position_id=f'position-{side}',
        symbol='AMD',
        side=side,
        amount=1000.0,
        entry_price=100.0,
        stop_loss=98.0 if side == 'BUY' else 102.0,
        take_profit=110.0 if side == 'BUY' else 90.0,
        opened_at=datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
        breakeven_stop_enabled=True,
        breakeven_trigger_percent=breakeven_trigger_percent,
        breakeven_buffer_percent=breakeven_buffer_percent,
        trailing_stop_enabled=False,
    )


def snapshot(last: float) -> MarketSnapshot:
    return MarketSnapshot.now(symbol='AMD', bid=last, ask=last, last=last)


def test_buy_net_breakeven_moves_stop_to_entry_plus_costs():
    tracker = PositionTracker()
    tracker.restore_open_position(
        tracked_position(
            side='BUY',
            breakeven_trigger_percent=1.3,
            breakeven_buffer_percent=0.3,
        )
    )

    close_signals = tracker.evaluate_snapshot(snapshot(101.31))

    assert close_signals == []
    position = tracker.open_positions_snapshot()[0]
    assert position.stop_loss == 100.3


def test_sell_net_breakeven_moves_stop_to_entry_minus_costs():
    tracker = PositionTracker()
    tracker.restore_open_position(
        tracked_position(
            side='SELL',
            breakeven_trigger_percent=1.3,
            breakeven_buffer_percent=0.3,
        )
    )

    close_signals = tracker.evaluate_snapshot(snapshot(98.69))

    assert close_signals == []
    position = tracker.open_positions_snapshot()[0]
    assert position.stop_loss == 99.7


def test_buy_net_breakeven_waits_until_gross_gain_covers_net_trigger():
    tracker = PositionTracker()
    tracker.restore_open_position(
        tracked_position(
            side='BUY',
            breakeven_trigger_percent=2.0,
            breakeven_buffer_percent=2.0,
        )
    )

    close_signals = tracker.evaluate_snapshot(snapshot(101.0))

    assert close_signals == []
    position = tracker.open_positions_snapshot()[0]
    assert position.stop_loss == 98.0
