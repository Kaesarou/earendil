from datetime import datetime, timezone

from app.execution.position_tracker import PositionTracker
from app.market.models import MarketSnapshot
from app.risk.models import TradePlan
from app.runtime.session_force_close import force_close_positions_before_session_end
from app.runtime.trading_session_window import TradingSessionDecision
from app.instruments.models import AssetClass


class FakeExecutor:
    def __init__(self):
        self.closed = []

    def close(self, position_id):
        self.closed.append(position_id)


class FakeRiskManager:
    def __init__(self):
        self.closed_symbols = []

    def record_close_position(self, symbol):
        self.closed_symbols.append(symbol)


class FakeJournal:
    def __init__(self):
        self.events = []

    def write(self, event_type, payload):
        self.events.append((event_type, payload))


def test_force_close_positions_before_session_end_closes_matching_position():
    now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
    tracker = PositionTracker()
    tracker.record_open_position(
        'p1',
        TradePlan(
            approved=True,
            reason='test_entry',
            symbol='AAPL',
            side='BUY',
            amount=100.0,
            stop_loss=99.0,
            take_profit=102.0,
        ),
        entry_price=100.0,
        opened_at=now,
    )
    executor = FakeExecutor()
    risk_manager = FakeRiskManager()
    journal = FakeJournal()

    force_close_positions_before_session_end(
        symbol='AAPL',
        snapshot=MarketSnapshot(symbol='AAPL', bid=100.0, ask=100.0, last=100.0, timestamp=now),
        session_decision=TradingSessionDecision(
            asset_class=AssetClass.EQUITY_US,
            session_active=True,
            session_24_7=False,
            collect_snapshots=True,
            new_entries_allowed=False,
            force_close_required=True,
            reason='force_close_before_session_end',
            session_start_time=None,
            session_end_time=None,
            time_until_session_end_minutes=10.0,
            session_key='test-session',
        ),
        executor=executor,
        position_tracker=tracker,
        risk_manager=risk_manager,
        trade_journal=journal,
        is_broker_authorization_error=lambda exc: False,
    )

    assert executor.closed == ['p1']
    assert risk_manager.closed_symbols == ['AAPL']
    assert journal.events[-1][0] == 'position_closed'
    assert journal.events[-1][1]['close_signal'].reason == 'force_close_before_session_end'
