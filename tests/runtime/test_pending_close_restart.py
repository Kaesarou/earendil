from datetime import datetime, timezone
from types import SimpleNamespace

from app.brokers.base import ClosePositionRejectedError
from app.execution.position_tracker import PositionCloseSignal, PositionTracker, TrackedPosition
from app.persistence.pending_close_store import PendingCloseStore
from app.persistence.position_store import PositionStore
from app.runtime.async_broker_operations import AsyncBrokerOperationsCoordinator
from app.runtime.broker_task_runner import BrokerTaskCompletion, BrokerTaskLane
from app.runtime.pending_close import CloseState, PendingClose

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)

class NoSubmitRunner:
    def __init__(self): self.submissions = []
    def has_pending_kind(self, kind): return False
    def submit(self, **task):
        self.submissions.append(task)
        return task.get('task_id') or task['kind']

class Journal:
    def __init__(self): self.events = []
    def write(self, event_type, payload): self.events.append((event_type, payload))

class Risk:
    def __init__(self): self.closed = []
    def record_close_position(self, symbol):
        self.closed.append(symbol)
        return 'session'
    def risk_profile_for(self, symbol):
        return SimpleNamespace(trade_cooldown=SimpleNamespace(enabled=False))

class Broker:
    def __init__(self): self.forgotten = []
    def forget_position_instrument(self, position_id): self.forgotten.append(position_id)

class CoordinatorFixture:
    def __init__(self, tmp_path):
        self.path = str(tmp_path / 'goblin.sqlite')
        self.position_store = PositionStore(self.path)
        self.pending_store = PendingCloseStore(self.path)
        self.tracker = PositionTracker()
        self.risk = Risk()
        self.runner = NoSubmitRunner()
        self.journal = Journal()
        self.broker = Broker()
        self.position = TrackedPosition(
            position_id='position-1', symbol='BTC', side='BUY', amount=500.0,
            entry_price=100.0, stop_loss=99.0, take_profit=102.0, opened_at=NOW,
        )
        self.signal = PositionCloseSignal(
            position_id='position-1', symbol='BTC', side='BUY', exit_price=98.9,
            reason='stop_loss', detected_at=NOW,
        )
        self.position_store.save_open_position(self.position)
        self.tracker.restore_open_position(self.position)
        self.coordinator = AsyncBrokerOperationsCoordinator(
            runner=self.runner, execution_broker=self.broker,
            rest_market_data=SimpleNamespace(), executor=SimpleNamespace(),
            position_tracker=self.tracker, risk_manager=self.risk,
            position_store=self.position_store,
            pending_close_store=self.pending_store,
            cooldown_store=SimpleNamespace(), trade_journal=self.journal,
            market_data_coordinator=SimpleNamespace(),
            is_broker_authorization_error=lambda exc: False,
        )


def test_restart_confirms_persisted_close_without_resubmitting(tmp_path):
    fixture = CoordinatorFixture(tmp_path)
    pending = PendingClose(
        position_id='position-1', symbol='BTC', signal=fixture.signal,
        source='websocket_position_guard', state=CloseState.PENDING_CONFIRMATION,
        requested_at=NOW, submitted_at=NOW, accepted_at=NOW,
        close_order_id='close-1', reference_id='ref-1',
    )
    fixture.pending_store.save(pending)

    fixture.coordinator.restore_pending_closes(
        fixture.pending_store.load_all(),
        open_states={'position-1': False},
        observed_at=NOW,
    )

    assert fixture.runner.submissions == []
    assert fixture.pending_store.load_all() == []
    assert fixture.position_store.load_open_positions() == []
    assert fixture.tracker.open_positions_snapshot() == []
    assert fixture.risk.closed == ['BTC']
    assert [event for event, _ in fixture.journal.events].count(
        'position_close_confirmed'
    ) == 1


def test_explicit_rejection_is_persisted_without_retry_or_risk_release(tmp_path):
    fixture = CoordinatorFixture(tmp_path)
    assert fixture.coordinator.submit_close(
        signal=fixture.signal,
        source='websocket_position_guard',
    )
    task = fixture.runner.submissions[0]
    error = ClosePositionRejectedError(
        position_id='position-1',
        message='broker rejected close',
        broker_response={'status': 'rejected'},
    )
    fixture.coordinator.handle_completion(
        BrokerTaskCompletion(
            task_id=task['task_id'], kind='close_position',
            lane=BrokerTaskLane.CLOSE, context=task['context'], error=error,
        ),
        now=NOW,
        latest_snapshots={},
    )

    assert len(fixture.runner.submissions) == 1
    assert fixture.pending_store.load_all()[0].state == CloseState.REJECTED
    assert fixture.tracker.open_positions_snapshot()
    assert fixture.position_store.load_open_positions()
    assert fixture.risk.closed == []
    assert 'position_close_rejected' in [event for event, _ in fixture.journal.events]
