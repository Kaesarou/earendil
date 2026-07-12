from datetime import datetime, timezone

from app.execution.position_tracker import TrackedPosition
from app.persistence.position_store import PositionStore


def test_position_store_persists_stale_position_fields(tmp_path):
    store = PositionStore(str(tmp_path / 'goblin.sqlite'))
    opened_at = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)

    store.save_open_position(
        TrackedPosition(
            position_id='position-1',
            symbol='AAPL',
            side='BUY',
            amount=500.0,
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=102.0,
            opened_at=opened_at,
            estimated_total_cost_percent=0.4,
            stale_position_enabled=True,
            stale_position_max_age_minutes=60,
            stale_position_min_favorable_move_percent=0.35,
            stale_position_buffer_percent=0.1,
        )
    )

    loaded = store.load_open_positions()[0]

    assert loaded.estimated_total_cost_percent == 0.4
    assert loaded.stale_position_enabled
    assert loaded.stale_position_max_age_minutes == 60
    assert loaded.stale_position_min_favorable_move_percent == 0.35
    assert loaded.stale_position_buffer_percent == 0.1
