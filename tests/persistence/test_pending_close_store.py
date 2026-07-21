from datetime import datetime, timezone

from app.execution.position_tracker import PositionCloseSignal, TrackedPosition
from app.persistence.pending_close_store import PendingCloseStore
from app.persistence.position_store import PositionStore
from app.runtime.pending_close import CloseState, PendingClose


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def tracked_position(position_id: str = 'position-1') -> TrackedPosition:
    return TrackedPosition(
        position_id=position_id,
        symbol='BTC',
        side='BUY',
        amount=500.0,
        entry_price=100.0,
        stop_loss=99.0,
        take_profit=102.0,
        opened_at=NOW,
    )


def pending_close(position_id: str = 'position-1') -> PendingClose:
    return PendingClose(
        position_id=position_id,
        symbol='BTC',
        signal=PositionCloseSignal(
            position_id=position_id,
            symbol='BTC',
            side='BUY',
            exit_price=98.9,
            reason='stop_loss',
            detected_at=NOW,
            metadata={'trigger': 'managed_stop'},
        ),
        source='websocket_position_guard',
        state=CloseState.SUBMISSION_UNKNOWN,
        requested_at=NOW,
        submitted_at=NOW,
        close_order_id='close-123',
        reference_id='ref-123',
        confirmation_checks=2,
        last_confirmation_at=NOW,
        last_error='network timeout',
        metadata={'session_decision_reason': 'open'},
    )


def test_pending_close_store_round_trips_full_close_state(tmp_path):
    store = PendingCloseStore(str(tmp_path / 'goblin.sqlite'))
    store.save(pending_close())

    loaded = store.load_all()
    assert len(loaded) == 1
    restored = loaded[0]
    assert restored.position_id == 'position-1'
    assert restored.symbol == 'BTC'
    assert restored.state == CloseState.SUBMISSION_UNKNOWN
    assert restored.signal.exit_price == 98.9
    assert restored.signal.reason == 'stop_loss'
    assert restored.signal.metadata == {'trigger': 'managed_stop'}
    assert restored.close_order_id == 'close-123'
    assert restored.reference_id == 'ref-123'
    assert restored.confirmation_checks == 2
    assert restored.last_error == 'network timeout'
    assert restored.metadata == {'session_decision_reason': 'open'}


def test_confirmed_close_deletes_pending_and_open_position_atomically(tmp_path):
    path = str(tmp_path / 'goblin.sqlite')
    position_store = PositionStore(path)
    pending_store = PendingCloseStore(path)
    position_store.save_open_position(tracked_position())
    pending_store.save(pending_close())

    pending_store.delete_with_open_position('position-1')

    assert pending_store.load_all() == []
    assert position_store.load_open_positions() == []
