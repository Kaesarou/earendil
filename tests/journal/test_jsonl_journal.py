import json
from datetime import datetime, timezone
from typing import NamedTuple

from app.journal.jsonl_journal import JsonlJournal


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
