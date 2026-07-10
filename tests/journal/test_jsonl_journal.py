import json
from datetime import datetime, timezone
from typing import NamedTuple

from app.instruments.models import AssetClass
from app.journal.jsonl_journal import JsonlJournal
from app.journal.serialization import serialize_value
from app.runtime.trading_session_window import TradingSessionDecision


class SessionDecisionStub(NamedTuple):
    session_key: str
    session_start_time: datetime
    session_end_time: datetime


def test_jsonl_journal_serializes_namedtuple_with_datetimes(tmp_path):
    journal_path = tmp_path / 'trades.jsonl'
    journal = JsonlJournal(str(journal_path))

    decision = SessionDecisionStub(
        session_key='EQUITY_US:2026-07-06T15:30:00+02:00:2026-07-06T22:00:00+02:00',
        session_start_time=datetime(2026, 7, 6, 15, 30, tzinfo=timezone.utc),
        session_end_time=datetime(2026, 7, 6, 22, 0, tzinfo=timezone.utc),
    )

    journal.write('session_started', {'session_decision': decision})

    record = json.loads(journal_path.read_text(encoding='utf-8'))

    assert record['event_type'] == 'session_started'
    assert record['payload']['session_decision'] == {
        'session_key': 'EQUITY_US:2026-07-06T15:30:00+02:00:2026-07-06T22:00:00+02:00',
        'session_start_time': '2026-07-06T15:30:00+00:00',
        'session_end_time': '2026-07-06T22:00:00+00:00',
    }


def test_trading_session_decision_with_asset_class_enum_is_json_serializable():
    decision = TradingSessionDecision(
        asset_class=AssetClass.EQUITY_EU,
        session_active=True,
        session_24_7=False,
        collect_snapshots=True,
        new_entries_allowed=True,
        force_close_required=False,
        reason='session_tradable',
        session_start_time=datetime(2026, 7, 10, 9, 0, tzinfo=timezone.utc),
        session_end_time=datetime(2026, 7, 10, 15, 30, tzinfo=timezone.utc),
        time_until_session_end_minutes=120.0,
        session_key='EQUITY_EU:2026-07-10T09:00:00+00:00:2026-07-10T15:30:00+00:00',
    )

    serialized = serialize_value({'session_decision': decision})

    json.dumps(serialized)
    assert serialized['session_decision']['asset_class'] == 'EQUITY_EU'
    assert serialized['session_decision']['session_start_time'] == '2026-07-10T09:00:00+00:00'
    assert serialized['session_decision']['session_end_time'] == '2026-07-10T15:30:00+00:00'
