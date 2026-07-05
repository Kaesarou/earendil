from datetime import datetime, timezone

from app.execution.position_tracker import TrackedPosition
from app.persistence.position_store import PositionStore


def position(position_id: str, symbol: str = 'MSFT') -> TrackedPosition:
    return TrackedPosition(
        position_id=position_id,
        symbol=symbol,
        side='BUY',
        amount=500.0,
        entry_price=100.0,
        stop_loss=99.0,
        take_profit=102.0,
        opened_at=datetime(2026, 6, 26, 16, 0, tzinfo=timezone.utc),
    )


def test_position_store_saves_loads_and_deletes_open_positions(tmp_path):
    store = PositionStore(str(tmp_path / 'earendil.sqlite'))

    store.save_open_position(position('position-1', 'MSFT'))
    store.save_open_position(position('position-2', 'NVDA'))

    loaded_positions = store.load_open_positions()

    assert [loaded.position_id for loaded in loaded_positions] == [
        'position-1',
        'position-2',
    ]
    assert loaded_positions[0].symbol == 'MSFT'
    assert loaded_positions[0].side == 'BUY'
    assert loaded_positions[0].amount == 500.0
    assert loaded_positions[0].entry_price == 100.0
    assert loaded_positions[0].stop_loss == 99.0
    assert loaded_positions[0].take_profit == 102.0

    store.delete_open_position('position-1')

    remaining_positions = store.load_open_positions()

    assert [loaded.position_id for loaded in remaining_positions] == [
        'position-2',
    ]


def test_position_store_replaces_existing_position(tmp_path):
    store = PositionStore(str(tmp_path / 'earendil.sqlite'))

    store.save_open_position(position('position-1', 'MSFT'))
    store.save_open_position(position('position-1', 'AAPL'))

    loaded_positions = store.load_open_positions()

    assert len(loaded_positions) == 1
    assert loaded_positions[0].position_id == 'position-1'
    assert loaded_positions[0].symbol == 'AAPL'
