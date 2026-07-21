from datetime import datetime, timezone
from types import SimpleNamespace

from app.brokers.base import (
    ClosePositionRejectedError,
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
from app.runtime.broker_task_runner import BrokerTaskCompletion, BrokerTaskLane
from app.runtime.pending_close import CloseState, PendingClose


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


class FakeRunner:
    def __init__(self) -> None:
        self.tasks: list[dict] = []

    def has_pending_kind(self, kind: str) -> bool:
        return any(item['kind'] == kind for item in self.tasks)

    def submit(self, **task):
        self.tasks.append(task)
        return task.get('task_id') or task['kind']


class FakeJournal:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def write(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


class FakeBroker:
    def __init__(self) -> None:
        self.forgotten: list[str] = []

    def forget_position_instrument(self, position_id: str) -> None:
        self.forgotten.append(position_id)


class FakeRiskManager:
    def __init__(self) -> None:
        self.closed_symbols: list[str] = []

    def record_close_position(self, symbol: str) -> str:
        self.closed_symbols.append(symbol)
        return 'session-1'

    def risk_profile_for(self, symbol: str):
        return SimpleNamespace(
            trade_cooldown=SimpleNamespace(enabled=False),
        )


class FakeMarketDataCoordinator:
    def mark_fallback_failed(self, symbols: list[str]) -> None:
        return None

    def mark_fallback_succeeded(self, symbols: list[str]) -> None:
        return None


class FakeExecutor:
    def close(self, position_id: str) -> ClosePositionSubmission:
        return ClosePositionSubmission(
            position_id=position_id,
            close_order_id=f'close-{position_id}',
            reference_id=f'ref-{position_id}',
            submitted_at=NOW,
            accepted_at=NOW,
            broker_response={'accepted': True},
        )


def position(position_id: str, symbol: str) -> TrackedPosition:
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


def signal(position_id: str, symbol: str) -> PositionCloseSignal:
    return PositionCloseSignal(
        position_id=position_id,
        symbol=symbol,
        side='BUY',
        exit_price=98.9,
        reason='stop_loss',
        detected_at=NOW,
    )


def pending_close(
    position_id: str,
    symbol: str,
    state: CloseState,
) -> PendingClose:
    return PendingClose(
        position_id=position_id,
        symbol=symbol,
        signal=signal(position_id, symbol),
        source='websocket_position_guard',
        state=state,
        requested_at=NOW,
        submitted_at=(
            NOW if state != CloseState.SUBMITTING else None
        ),
        accepted_at=(
            NOW if state == CloseState.PENDING_CONFIRMATION else None
        ),
        close_order_id=(
            'close-order-1'
            if state == CloseState.PENDING_CONFIRMATION
            else None
        ),
        reference_id=(
            'reference-1'
            if state == CloseState.PENDING_CONFIRMATION
            else None
        ),
    )


def build_coordinator(tmp_path):
    path = str(tmp_path / 'goblin.sqlite')
    tracker = PositionTracker()
    positions = [
        position('position-a', 'BTC'),
        position('position-b', 'ETH'),
    ]
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
    return (
        coordinator,
        runner,
        journal,
        tracker,
        risk,
        pending_store,
        position_store,
        broker,
    )


def completion_for(task, *, value=None, error=None) -> BrokerTaskCompletion:
    return BrokerTaskCompletion(
        task_id=task.get('task_id') or task['kind'],
        kind=task['kind'],
        lane=BrokerTaskLane.CLOSE,
        context=task['context'],
        value=value,
        error=error,
    )


def event_types(journal: FakeJournal) -> list[str]:
    return [event_type for event_type, _ in journal.events]


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
    assert event_types(journal).count('position_close_requested') == 1


def test_nearby_closes_are_queued_without_waiting_for_confirmation(tmp_path):
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


def test_accepted_submission_keeps_risk_until_portfolio_absence(tmp_path):
    (
        coordinator,
        runner,
        journal,
        tracker,
        risk,
        pending_store,
        position_store,
        _,
    ) = build_coordinator(tmp_path)
    coordinator.submit_close(
        signal=signal('position-a', 'BTC'),
        source='websocket_position_guard',
    )
    task = runner.tasks[0]

    coordinator.handle_completion(
        completion_for(task, value=task['operation']()),
        now=NOW,
        latest_snapshots={},
    )

    assert tracker.positions['position-a'].symbol == 'BTC'
    assert risk.closed_symbols == []
    assert {item.position_id for item in position_store.load_open_positions()} == {
        'position-a',
        'position-b',
    }
    assert pending_store.load_all()[0].state == CloseState.PENDING_CONFIRMATION
    assert 'position_close_submitted' in event_types(journal)


def test_ambiguous_submission_confirms_from_one_portfolio_absence(tmp_path):
    (
        coordinator,
        runner,
        journal,
        tracker,
        risk,
        pending_store,
        position_store,
        broker,
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
        close_order_id='close-order-1',
        reference_id='reference-1',
    )

    coordinator.handle_completion(
        completion_for(task, error=error),
        now=NOW,
        latest_snapshots={},
    )

    assert len(runner.tasks) == 1
    restored = pending_store.load_all()[0]
    assert restored.state == CloseState.SUBMISSION_UNKNOWN
    assert restored.close_order_id == 'close-order-1'
    assert restored.reference_id == 'reference-1'
    assert 'position-a' in tracker.positions
    assert risk.closed_symbols == []

    runner.tasks.clear()
    assert coordinator.schedule_reconciliation(now=NOW)
    scheduled = runner.tasks[0]
    coordinator.handle_completion(
        BrokerTaskCompletion(
            task_id='reconcile-1',
            kind='position_reconciliation',
            lane=BrokerTaskLane.STANDARD,
            context=scheduled['context'],
            value={'position-a': False, 'position-b': True},
        ),
        now=NOW,
        latest_snapshots={},
    )

    assert 'position-a' not in tracker.positions
    assert risk.closed_symbols == ['BTC']
    assert pending_store.load_all() == []
    assert [item.position_id for item in position_store.load_open_positions()] == [
        'position-b'
    ]
    assert broker.forgotten == ['position-a']
    assert 'position_close_confirmed' in event_types(journal)


def test_explicit_rejection_keeps_position_and_requires_intervention(tmp_path):
    (
        coordinator,
        runner,
        journal,
        tracker,
        risk,
        pending_store,
        position_store,
        _,
    ) = build_coordinator(tmp_path)
    coordinator.submit_close(
        signal=signal('position-a', 'BTC'),
        source='websocket_position_guard',
    )
    task = runner.tasks[0]
    error = ClosePositionRejectedError(
        position_id='position-a',
        message='business rejection',
        broker_response={'errorCode': 42},
    )

    coordinator.handle_completion(
        completion_for(task, error=error),
        now=NOW,
        latest_snapshots={},
    )

    assert pending_store.load_all()[0].state == CloseState.REJECTED
    assert 'position-a' in tracker.positions
    assert risk.closed_symbols == []
    assert {item.position_id for item in position_store.load_open_positions()} == {
        'position-a',
        'position-b',
    }
    assert event_types(journal).count('position_close_rejected') == 1
    assert (
        event_types(journal).count(
            'position_close_manual_intervention_required'
        )
        == 1
    )


def test_restart_restores_pending_without_reissuing_post(tmp_path):
    (
        coordinator,
        runner,
        journal,
        tracker,
        risk,
        pending_store,
        position_store,
        broker,
    ) = build_coordinator(tmp_path)
    pending_store.save(
        pending_close(
            'position-a',
            'BTC',
            CloseState.PENDING_CONFIRMATION,
        )
    )

    coordinator.restore_pending_closes(
        pending_store.load_all(),
        open_states={'position-a': False, 'position-b': True},
        observed_at=NOW,
    )

    assert runner.tasks == []
    assert 'position-a' not in tracker.positions
    assert risk.closed_symbols == ['BTC']
    assert pending_store.load_all() == []
    assert [item.position_id for item in position_store.load_open_positions()] == [
        'position-b'
    ]
    assert broker.forgotten == ['position-a']
    assert 'position_close_confirmed' in event_types(journal)


def test_restart_during_submission_becomes_unknown_without_post(tmp_path):
    (
        coordinator,
        runner,
        journal,
        tracker,
        risk,
        pending_store,
        position_store,
        _,
    ) = build_coordinator(tmp_path)
    pending_store.save(
        pending_close('position-a', 'BTC', CloseState.SUBMITTING)
    )

    coordinator.restore_pending_closes(
        pending_store.load_all(),
        open_states={'position-a': True, 'position-b': True},
        observed_at=NOW,
    )

    assert runner.tasks == []
    restored = pending_store.load_all()[0]
    assert restored.state == CloseState.SUBMISSION_UNKNOWN
    assert 'position-a' in tracker.positions
    assert risk.closed_symbols == []
    assert {item.position_id for item in position_store.load_open_positions()} == {
        'position-a',
        'position-b',
    }
    assert 'position_close_submission_unknown' in event_types(journal)
