from datetime import datetime, timezone

from app.execution.position_tracker import PositionTracker, TrackedPosition


def test_position_tracker_removes_position_without_close_signal():
    tracker = PositionTracker()
    position = TrackedPosition(
        position_id='position-1',
        symbol='AMD',
        side='SELL',
        amount=500.0,
        entry_price=100.0,
        stop_loss=101.0,
        take_profit=98.0,
        opened_at=datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
    )
    tracker.restore_open_position(position)

    removed_position = tracker.remove_position('position-1')

    assert removed_position is not None
    assert removed_position.position_id == 'position-1'
    assert not tracker.has_open_positions()
