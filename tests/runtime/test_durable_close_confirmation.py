from datetime import datetime, timezone
from types import SimpleNamespace

from app.brokers.base import (
    ClosePositionSubmission,
    ClosePositionSubmissionUnknownError,
)
from app.execution.position_tracker import (
    PositionCloseSignal,
    PositionTracker,
    TrackedPosition,
)
from app.persistence.pending_close_store import PendingCloseStore
from app.persistence.position_store import PositionStore
from app.runtime.async_broker_operations import AsyncBrokerOperationsCoordinator
from app.runtime.broker_task_runner import (
    BrokerTaskCompletion,
    BrokerTaskLane,
)
from app.runtime.pending_close import CloseState


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


class FakeRunner:
    def __init__(self):
        self.tasks = []

    def has_pending_kind(self, kind):
        return any(item['kind'] == kind for item in self.tasks)

    def submit(self, **task):
        self.tasks.append(task)
        return task.get('task_id') or task['kind']


class FakeJournal:
    def __init__(self):
        self.events = []

    def write(self, event_type, payload):
        self.events.append((event_type, payload))


class FakeBroker:
    def __init__(self):
        self.forgotten = []

    def forget_position_instrument(self, position_id):
        self.forgotten.append(position_id)


class FakeRiskManager:
    def __init__(self):
        self.closed_symbols = []

    def record_close_position(self, symbol):
        self.closed_symbols.append(symbol)
        return 'session-1'

    def risk_profile_for(self, symbol):
        return SimpleNamespace(
            trade_cooldown=SimpleNamespace(enabled=False)
        )


class FakeMarketDataCoordinator:
    def mark_fallback_failed(self, symbols):
        return None

    def mark_fallback_succeeded(self, symbols):
        return None


class FakeExecutor:
    def close(self, position_id):
        return ClosePositionSubmission(
            position_id=position_id,
            close_order_id=f'close-{position_id}',
            reference_id=f'ref-{position_id}',
            submitted_at=NOW,
            accepted_at=NOW,
            broker_response={'accepted': True},
        )


def position(position_id, symbol):
    return TrackedPosition(
        position_id=position_id,
        symbol=symbol,
        side='BUY',
        amount=500.0,
        entry_price=100.0,
        stop_loss=99.0,
        take_profit=102.0,
        opened_at=NOW,
    )


def signal(position_id, symbol):
    return PositionCloseSignal(
        position_id=position_id,
        symbol=symbol,
        side='BUY',
        exit_price=98.9,
        reason='stop_loss',
        detected_at=NOW,
    )


def build_coordinator(tmp_path):
    path = str(tmp_path / 'goblin.sqlite')
    tracker = PositionTracker()
    positions = [position('position-a', 'BTC'), position('position-b', 'ETH')]
    position_store = PositionStore(path)
    for item in positions:
        tracker.restore_open_position(item)
        position_store.save_open_position(item)
    runner = FakeRunner()
    journal = FakeJournal()
    risk = FakeRiskManager()
    pending_store = PendingCloseStore(path)
    broker = FakeBroker()
    coordinator = AsyncBrokerOperationsCoordinator(
        runner=runner,
        execution_broker=broker,
        rest_market_data=SimpleNamespace(),
        executor=FakeExecutor(),
        position_tracker=tracker,
        risk_manager=risk,
        position_store=position_store,
        pending_close_store=pending_store,
        cooldown_store=SimpleNamespace(),
        trade_journal=journal,
        market_data_coordinator=FakeMarketDataCoordinator(),
        is_broker_authorization_error=lambda exc: False,
    )
    return coordinator, runner, journal, tracker, risk, pending_store, position_store


def completion_for(task, *, value=None, error=None):
    return BrokerTaskCompletion(
        task_id=task.get('task_id') or task['kind'],
        kind=task['kind'],
        lane=BrokerTaskLane.CLOSE,
        context=task['context'],
        value=value,
        error=error,
    )


def test_repeated_signals_create_one_request_and_one_post(tmp_path):
    coordinator, runner, journal, *_ = build_coordinator(tmp_path)

    assert coordinator.submit_close(
        signal=signal('position-a', 'BTC'),
        source='websocket_position_guard',
    )
    assert not coordinator.submit_close(
        signal=signal('position-a', 'BTC'),
        source='websocket_position_guard',
    )

    assert len(runner.tasks) == 1
    assert [event for event, _ in journal.events].count(
        'position_close_requested'
    ) == 1


def test_nearby_closes_are_both_queued_without_waiting_for_confirmation(tmp_path):
    coordinator, runner, *_ = build_coordinator(tmp_path)

    assert coordinator.submit_close(
        signal=signal('position-a', 'BTC'),
        source='websocket_position_guard',
    )
    assert coordinator.submit_close(
        signal=signal('position-b', 'ETH'),
        source='websocket_position_guard',
    )

    assert [task['task_id'] for task in runner.tasks] == [
        'close_position:position-a',
        'close_position:position-b',
    ]


def test_accepted_submission_keeps_position_and_risk_until_portfolio_absence(tmp_path):
    (
        coordinator,
        runner,
        journal,
        tracker,
        risk,
        pending_store,
        position_store,
    ) = build_coordinator(tmp_path)
    coordinator.submit_close(
        signal=signal('position-a', 'BTC'),
        source='websocket_position_guard',
    )
    task = runner.tasks[0]
    submission = task['operation']()

    coordinator.handle_completion(
        completion_for(task, value=submission),
        now=NOW,
        latest_snapshots={},
    )

    assert tracker.positions['position-a'].symbol == 'BTC'
    assert risk.closed_symbols == []
    assert position_store.load_open_positions()
    assert pending_store.load_all()[0].state == CloseState.PENDING_CONFIRMATION
    assert 'position_close_submitted' in [event for event, _ in journal.events]


def test_ambiguous_submission_never_retries_and_confirms_from_one_absence(tmp_path):
    (
        coordinator,
        runner,
        journal,
        tracker,
        risk,
        pending_store,
        position_store,
    ) = build_coordinator(tmp_path)
    coordinator.submit_close(
        signal=signal('position-a', 'BTC'),
        source='websocket_position_guard',
    )
    task = runner.tasks[0]
    error = ClosePositionSubmissionUnknownError(
        position_id='position-a',
        submitted_at=NOW,
        cause=TimeoutError('network timeout'),
    )
    coordinator.handle_completion(
        completion_for(task, error=error),
        now=NOW,
        latest_snapshots={},
    )

    assert len(runner.tasks) == 1
    assert pending_store.load_all()[0].state == CloseState.SUBMISSION_UNKNOWN
    assert 'position-a' in tracker.positions
    assert risk.closed_symbols == []

    reconciliation = BrokerTaskCompletion(
        task_id='reconcile-1',
        kind='position_reconciliation',
        lane=BrokerTaskLane.STANDARD,
        context=SimpleNamespace(),
        value={'position-a': False, 'position-b': True},
    )
    reconciliation_context = coordinator.schedule_reconciliation(now=NOW)
    assert reconciliation_context is False
    scheduled = next(
        task for task in runner.tasks if task['kind'] == 'position_reconciliation'
    ) if any(task['kind'] == 'position_reconciliation' for task in runner.tasks) else None
    if scheduled is None:
        coordinator.runner.tasks = []
        assert coordinator.schedule_reconciliation(now=NOW)
        scheduled = coordinator.runner.tasks[0]
    reconciliation = BrokerTaskCompletion(
        task_id='reconcile-1',
        kind='position_reconciliation',
        lane=BrokerTaskLane.STANDARD,
        context=scheduled['context'],
        value={'position-a': False, 'position-b': True},
    )
    coordinator.handle_completion(
        reconciliation,
        now=NOW,
        latest_snapshots={},
    )

    assert 'position-a' not in tracker.positions
    assert risk.closed_symbols == ['BTC']
    assert pending_store.load_all() == []
    assert [item.position_id for item in position_store.load_open_positions()] == [
        'position-b'
    ]
    assert 'position_close_confirmed' in [event for event, _ in journal.events]
