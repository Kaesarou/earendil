import logging
from datetime import datetime, timedelta, timezone

from app.runtime.runtime_heartbeat import RuntimeHeartbeat


class FakeJournal:
    def __init__(self):
        self.events = []

    def write(self, event_type, payload):
        self.events.append((event_type, payload))


def test_runtime_heartbeat_emits_only_after_interval():
    heartbeat = RuntimeHeartbeat(interval_minutes=5)
    journal = FakeJournal()
    now = heartbeat.last_emitted_at

    assert not heartbeat.maybe_emit(
        journal=journal,
        logger=logging.getLogger('test'),
        metrics={'market_snapshots': 10, 'candles_closed': 2},
        open_positions=0,
        active_symbols=3,
        now=now + timedelta(minutes=4),
    )
    assert heartbeat.maybe_emit(
        journal=journal,
        logger=logging.getLogger('test'),
        metrics={
            'market_snapshots': 20,
            'candles_closed': 4,
            'candidates': 1,
            'orders_submitted': 0,
            'errors': 0,
        },
        open_positions=0,
        active_symbols=3,
        now=now + timedelta(minutes=5),
    )

    assert journal.events == [
        (
            'session_heartbeat',
            {
                'market_snapshots': 20,
                'candles_closed': 4,
                'candidates': 1,
                'orders_submitted': 0,
                'errors': 0,
                'open_positions': 0,
                'active_symbols': 3,
            },
        )
    ]
