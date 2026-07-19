from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast

from app.brokers.base import BrokerClient, OpenPositionResult
from app.execution.position_tracker import PositionTracker, TrackedPosition
from app.journal.jsonl_journal import JsonlJournal
from app.market.models import MarketSnapshot
from app.persistence.position_store import PositionStore
from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.risk_manager import RiskManager
from app.runtime.position_lifecycle import reconcile_externally_closed_positions


class BatchPositionBroker(BrokerClient):
    def __init__(
        self,
        states: dict[str, bool],
        error: Exception | None = None,
    ):
        self.states = states
        self.error = error
        self.batch_calls = 0
        self.requested_position_ids: list[str] = []

    def get_position_open_states(
        self,
        position_ids: list[str],
    ) -> dict[str, bool]:
        self.batch_calls += 1
        self.requested_position_ids = position_ids
        if self.error is not None:
            raise self.error
        return {
            position_id: self.states[position_id]
            for position_id in position_ids
        }

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        raise NotImplementedError

    def get_market_snapshots(
        self,
        symbols: list[str],
    ) -> dict[str, MarketSnapshot]:
        raise NotImplementedError

    def get_account_equity(self) -> float:
        raise NotImplementedError

    def open_position(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_loss: float,
        take_profit: float,
    ) -> OpenPositionResult:
        raise NotImplementedError

    def close_position(self, position_id: str) -> None:
        raise NotImplementedError

    def is_position_open(self, position_id: str) -> bool:
        raise AssertionError('individual position lookup must not be used')


class StoreStub:
    def __init__(self):
        self.deleted_position_ids: list[str] = []

    def delete_open_position(self, position_id: str) -> None:
        self.deleted_position_ids.append(position_id)


class RiskManagerStub:
    def __init__(self):
        self.closed_symbols: list[str] = []

    def record_close_position(self, symbol: str) -> str:
        self.closed_symbols.append(symbol)
        return 'test-session'

    def risk_profile_for(self, symbol: str):
        return SimpleNamespace(
            trade_cooldown=SimpleNamespace(enabled=False)
        )


class JournalStub:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def write(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


def tracked_position(position_id: str, symbol: str) -> TrackedPosition:
    return TrackedPosition(
        position_id=position_id,
        symbol=symbol,
        side='BUY',
        amount=10.0,
        entry_price=100.0,
        stop_loss=99.0,
        take_profit=102.0,
        opened_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )


def reconcile(
    *,
    broker: BatchPositionBroker,
    tracker: PositionTracker,
    store: StoreStub,
    risk_manager: RiskManagerStub,
    journal: JournalStub,
) -> None:
    reconcile_externally_closed_positions(
        broker=broker,
        position_tracker=tracker,
        risk_manager=cast(RiskManager, risk_manager),
        position_store=cast(PositionStore, store),
        cooldown_store=cast(TradeCooldownStore, None),
        trade_journal=cast(JsonlJournal, journal),
        is_broker_authorization_error=lambda exc: False,
    )


def test_reconciliation_uses_one_batch_and_removes_closed_position():
    tracker = PositionTracker()
    tracker.restore_open_position(tracked_position('position-1', 'BTC'))
    tracker.restore_open_position(tracked_position('position-2', 'ETH'))
    broker = BatchPositionBroker(
        {'position-1': True, 'position-2': False}
    )
    store = StoreStub()
    risk_manager = RiskManagerStub()
    journal = JournalStub()

    reconcile(
        broker=broker,
        tracker=tracker,
        store=store,
        risk_manager=risk_manager,
        journal=journal,
    )

    assert broker.batch_calls == 1
    assert broker.requested_position_ids == ['position-1', 'position-2']
    assert [
        position.position_id
        for position in tracker.open_positions_snapshot()
    ] == ['position-1']
    assert store.deleted_position_ids == ['position-2']
    assert risk_manager.closed_symbols == ['ETH']
    assert 'position_reconciled_closed' in {
        event_type for event_type, _ in journal.events
    }


def test_reconciliation_snapshot_error_keeps_all_positions():
    tracker = PositionTracker()
    tracker.restore_open_position(tracked_position('position-1', 'BTC'))
    tracker.restore_open_position(tracked_position('position-2', 'ETH'))
    broker = BatchPositionBroker({}, error=RuntimeError('portfolio down'))
    store = StoreStub()
    risk_manager = RiskManagerStub()
    journal = JournalStub()

    reconcile(
        broker=broker,
        tracker=tracker,
        store=store,
        risk_manager=risk_manager,
        journal=journal,
    )

    assert broker.batch_calls == 1
    assert len(tracker.open_positions_snapshot()) == 2
    assert store.deleted_position_ids == []
    assert risk_manager.closed_symbols == []
    assert [event_type for event_type, _ in journal.events] == [
        'position_reconciliation_warning'
    ]
