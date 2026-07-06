from datetime import datetime, timezone

from app.execution.position_tracker import TrackedPosition
from app.persistence.position_store import PositionStore


def position(
    position_id: str,
    symbol: str = 'MSFT',
    entry_price: float = 100.0,
    stop_loss: float = 99.0,
    take_profit: float = 102.0,
) -> TrackedPosition:
    return TrackedPosition(
        position_id=position_id,
        symbol=symbol,
        side='BUY',
        amount=500.0,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        opened_at=datetime(2026, 6, 26, 16, 0, tzinfo=timezone.utc),
    )


def test_position_store_saves_loads_and_deletes_open_positions(tmp_path):
    store = PositionStore(str(tmp_path / 'earendil.sqlite'))

    store.save_open_position(position('position-1', 'MSFT'))
    store.save_open_position(position('position-2', 'NVDA'))

    loaded_positions = store.load_open_positions()

    assert [loaded.position_id for loaded in loaded_positions] == ['position-1', 'position-2']
    assert loaded_positions[0].symbol == 'MSFT'
    assert loaded_positions[0].side == 'BUY'
    assert loaded_positions[0].amount == 500.0
    assert loaded_positions[0].entry_price == 100.0
    assert loaded_positions[0].stop_loss == 99.0
    assert loaded_positions[0].take_profit == 102.0

    store.delete_open_position('position-1')

    remaining_positions = store.load_open_positions()

    assert [loaded.position_id for loaded in remaining_positions] == ['position-2']


def test_position_store_persists_adjusted_execution_price_levels(tmp_path):
    store = PositionStore(str(tmp_path / 'earendil.sqlite'))

    store.save_open_position(position('position-1', 'HO.PA', entry_price=238.0, stop_loss=236.096, take_profit=241.332))

    loaded = store.load_open_positions()[0]

    assert loaded.entry_price == 238.0
    assert loaded.stop_loss == 236.096
    assert loaded.take_profit == 241.332


def test_position_store_persists_managed_stop_fields(tmp_path):
    store = PositionStore(str(tmp_path / 'earendil.sqlite'))
    managed_position = position('position-1')
    managed_position = TrackedPosition(
        **{
            **managed_position.__dict__,
            'trailing_stop_net_buffer_percent': 0.1,
            'managed_stop_protection_type': 'trailing',
        }
    )

    store.save_open_position(managed_position)

    loaded = store.load_open_positions()[0]

    assert loaded.trailing_stop_net_buffer_percent == 0.1
    assert loaded.managed_stop_protection_type == 'trailing'
    assert loaded.last_stop_update_metadata is None


def test_position_store_replaces_existing_position(tmp_path):
    store = PositionStore(str(tmp_path / 'earendil.sqlite'))

    store.save_open_position(position('position-1', 'MSFT'))
    store.save_open_position(position('position-1', 'AAPL'))

    loaded_positions = store.load_open_positions()

    assert len(loaded_positions) == 1
    assert loaded_positions[0].position_id == 'position-1'
    assert loaded_positions[0].symbol == 'AAPL'
