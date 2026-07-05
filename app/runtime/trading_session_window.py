from datetime import datetime, time, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo

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


class TradingSessionService:
    def __init__(
        self,
        configs: dict[AssetClass, AssetTradingSessionConfig],
        timezone_name: str,
    ):
        self.configs = configs
        self.timezone = ZoneInfo(timezone_name)

    def evaluate(self, *, asset_class: AssetClass, now: datetime) -> TradingSessionDecision:
        config = self.configs[asset_class]
        if config.is_24_7:
            return TradingSessionDecision(
                asset_class=asset_class,
                session_active=True,
                session_24_7=True,
                collect_snapshots=True,
                new_entries_allowed=True,
                force_close_required=False,
                reason=SESSION_TRADABLE,
                session_start_time=None,
                session_end_time=None,
                time_until_session_end_minutes=None,
                session_key=asset_class.value + ':24_7',
            )
        return TradingSessionDecision(
            asset_class=asset_class,
            session_active=False,
            session_24_7=False,
            collect_snapshots=False,
            new_entries_allowed=False,
            force_close_required=False,
            reason=SESSION_CLOSED,
            session_start_time=None,
            session_end_time=None,
            time_until_session_end_minutes=None,
            session_key=None,
        )

    def _to_local_time(self, now: datetime) -> datetime:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(self.timezone)


def parse_trading_sessions(raw_sessions: str) -> tuple[TradingSessionWindow, ...]:
    sessions: list[TradingSessionWindow] = []
    for raw_session in raw_sessions.split(','):
        value = raw_session.strip()
        if not value:
            continue
        raw_start, raw_end = value.split('-', maxsplit=1)
        sessions.append(
            TradingSessionWindow(
                start=_parse_time(raw_start.strip()),
                end=_parse_time(raw_end.strip()),
            )
        )
    return tuple(sessions)


def _parse_time(raw_value: str) -> time:
    hour, minute = raw_value.split(':', maxsplit=1)
    return time(hour=int(hour), minute=int(minute))
