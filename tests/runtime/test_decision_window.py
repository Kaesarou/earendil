from datetime import datetime, timedelta, timezone

from app.runtime.decision_window import DecisionWindowCoordinator


NOW = datetime(2026, 7, 20, 0, 1, tzinfo=timezone.utc)


def test_window_waits_for_all_symbols_or_grace_expiry():
    windows = DecisionWindowCoordinator(grace_seconds=5)
    assert windows.record(
        closed_at=NOW,
        symbol='BTC',
        expected_symbols=['BTC', 'ETH'],
        candidate=None,
    )
    assert windows.pop_ready(now=NOW + timedelta(seconds=4)) == []
    assert windows.pop_ready(now=NOW + timedelta(seconds=5)) == [[]]


def test_finalized_minute_cannot_be_reopened_by_late_event():
    windows = DecisionWindowCoordinator(grace_seconds=1)
    assert windows.record(
        closed_at=NOW,
        symbol='BTC',
        expected_symbols=['BTC'],
        candidate=None,
    )
    assert windows.pop_ready(now=NOW) == [[]]
    assert windows.record(
        closed_at=NOW,
        symbol='ETH',
        expected_symbols=['BTC', 'ETH'],
        candidate=None,
    ) is False
