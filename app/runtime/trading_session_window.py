from datetime import datetime, time
from typing import NamedTuple

from app.instruments.models import AssetClass


SESSION_CLOSED = 'session_closed'
SESSION_TRADABLE = 'session_tradable'
TOO_CLOSE_TO_SESSION_END = 'too_close_to_session_end'
FORCE_CLOSE_BEFORE_SESSION_END = 'force_close_before_session_end'

NEW_ENTRIES_CUTOFF_MINUTES_BEFORE_SESSION_END = 60
FORCE_CLOSE_MINUTES_BEFORE_SESSION_END = 20


class TradingSessionWindow(NamedTuple):
    start: time
    end: time

    @property
    def crosses_midnight(self) -> bool:
        return self.end <= self.start


class AssetTradingSessionConfig(NamedTuple):
    asset_class: AssetClass
    sessions: tuple[TradingSessionWindow, ...]

    @property
    def is_24_7(self) -> bool:
        return not self.sessions


class TradingSessionDecision(NamedTuple):
    asset_class: AssetClass
    session_active: bool
    session_24_7: bool
    collect_snapshots: bool
    new_entries_allowed: bool
    force_close_required: bool
    reason: str
    session_start_time: datetime | None
    session_end_time: datetime | None
    time_until_session_end_minutes: float | None
    session_key: str | None
