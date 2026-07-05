from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config.settings import Settings
from app.instruments.models import AssetClass

SESSION_CLOSED = 'session_closed'
SESSION_TRADABLE = 'session_tradable'
TOO_CLOSE_TO_SESSION_END = 'too_close_to_session_end'
FORCE_CLOSE_BEFORE_SESSION_END = 'force_close_before_session_end'


@dataclass(frozen=True)
class TradingSessionWindow:
    start: time
    end: time

    @property
    def crosses_midnight(self) -> bool:
        return self.end <= self.start


@dataclass(frozen=True)
class AssetTradingSessionConfig:
    asset_class: AssetClass
    sessions: tuple[TradingSessionWindow, ...]

    @property
    def is_24_7(self) -> bool:
        return not self.sessions


@dataclass(frozen=True)
class TradingSessionDecision:
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


class TradingSessionState:
    def __init__(self):
        self._active_session_key_by_symbol: dict[str, str | None] = {}

    def mark_and_detect_new_session(
        self,
        *,
        symbol: str,
        decision: TradingSessionDecision,
    ) -> bool:
        previous_key = self._active_session_key_by_symbol.get(symbol)
        current_key = decision.session_key if decision.session_active else None
        self._active_session_key_by_symbol[symbol] = current_key
        return current_key is not None and current_key != previous_key


class TradingSessionService:
    NEW_ENTRIES_CUTOFF_MINUTES_BEFORE_SESSION_END = 60
    FORCE_CLOSE_MINUTES_BEFORE_SESSION_END = 20

    def __init__(
        self,
        configs: dict[AssetClass, AssetTradingSessionConfig],
        timezone_name: str,
    ):
        self.configs = configs
        self.timezone = ZoneInfo(timezone_name)

    def evaluate(
        self,
        *,
        asset_class: AssetClass,
        now: datetime,
    ) -> TradingSessionDecision:
        config = self.configs[asset_class]
        local_now = self._to_local_time(now)

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
                session_key=f'{asset_class.value}:24_7',
            )

        active_session = self._active_session(config.sessions, local_now)
        if active_session is None:
            next_session = self._next_session(config.sessions, local_now)
            return TradingSessionDecision(
                asset_class=asset_class,
                session_active=False,
                session_24_7=False,
                collect_snapshots=False,
                new_entries_allowed=False,
                force_close_required=False,
                reason=SESSION_CLOSED,
                session_start_time=next_session[0] if next_session else None,
                session_end_time=next_session[1] if next_session else None,
                time_until_session_end_minutes=None,
                session_key=None,
            )

        session_start, session_end = active_session
        minutes_until_end = max(0.0, (session_end - local_now).total_seconds() / 60)
        reason = SESSION_TRADABLE
        new_entries_allowed = True
        force_close_required = False

        if minutes_until_end <= self.FORCE_CLOSE_MINUTES_BEFORE_SESSION_END:
            reason = FORCE_CLOSE_BEFORE_SESSION_END
            new_entries_allowed = False
            force_close_required = True
        elif minutes_until_end <= self.NEW_ENTRIES_CUTOFF_MINUTES_BEFORE_SESSION_END:
            reason = TOO_CLOSE_TO_SESSION_END
            new_entries_allowed = False

        return TradingSessionDecision(
            asset_class=asset_class,
            session_active=True,
            session_24_7=False,
            collect_snapshots=True,
            new_entries_allowed=new_entries_allowed,
            force_close_required=force_close_required,
            reason=reason,
            session_start_time=session_start,
            session_end_time=session_end,
            time_until_session_end_minutes=round(minutes_until_end, 4),
            session_key=self._session_key(asset_class, session_start, session_end),
        )

    def _active_session(
        self,
        sessions: tuple[TradingSessionWindow, ...],
        local_now: datetime,
    ) -> tuple[datetime, datetime] | None:
        for session in sessions:
            start_at, end_at = self._session_bounds_for_now(session, local_now)
            if start_at <= local_now < end_at:
                return start_at, end_at
        return None

    def _next_session(
        self,
        sessions: tuple[TradingSessionWindow, ...],
        local_now: datetime,
    ) -> tuple[datetime, datetime] | None:
        candidates: list[tuple[datetime, datetime]] = []
        for days_offset in range(0, 2):
            day = local_now.date() + timedelta(days=days_offset)
            for session in sessions:
                start_at = datetime.combine(day, session.start, tzinfo=self.timezone)
                end_day = day + timedelta(days=1) if session.crosses_midnight else day
                end_at = datetime.combine(end_day, session.end, tzinfo=self.timezone)
                if start_at > local_now:
                    candidates.append((start_at, end_at))
        return min(candidates, key=lambda candidate: candidate[0]) if candidates else None

    def _session_bounds_for_now(
        self,
        session: TradingSessionWindow,
        local_now: datetime,
    ) -> tuple[datetime, datetime]:
        today = local_now.date()
        start_at = datetime.combine(today, session.start, tzinfo=self.timezone)
        end_day = today + timedelta(days=1) if session.crosses_midnight else today
        end_at = datetime.combine(end_day, session.end, tzinfo=self.timezone)

        if session.crosses_midnight and local_now.time() < session.end:
            start_at -= timedelta(days=1)
            end_at -= timedelta(days=1)

        return start_at, end_at

    def _to_local_time(self, now: datetime) -> datetime:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(self.timezone)

    def _session_key(
        self,
        asset_class: AssetClass,
        session_start: datetime,
        session_end: datetime,
    ) -> str:
        return f'{asset_class.value}:{session_start.isoformat()}:{session_end.isoformat()}'


def trading_session_service_from_settings(settings: Settings) -> TradingSessionService:
    return TradingSessionService(
        configs={
            AssetClass.CRYPTO: AssetTradingSessionConfig(
                asset_class=AssetClass.CRYPTO,
                sessions=parse_trading_sessions(settings.trading_sessions_crypto),
            ),
            AssetClass.EQUITY_US: AssetTradingSessionConfig(
                asset_class=AssetClass.EQUITY_US,
                sessions=parse_trading_sessions(settings.trading_sessions_equity_us),
            ),
            AssetClass.EQUITY_EU: AssetTradingSessionConfig(
                asset_class=AssetClass.EQUITY_EU,
                sessions=parse_trading_sessions(settings.trading_sessions_equity_eu),
            ),
        },
        timezone_name=settings.trading_session_timezone,
    )


def parse_trading_sessions(raw_sessions: str) -> tuple[TradingSessionWindow, ...]:
    sessions: list[TradingSessionWindow] = []
    for raw_session in raw_sessions.split(','):
        value = raw_session.strip()
        if not value:
            continue
        try:
            raw_start, raw_end = value.split('-', maxsplit=1)
        except ValueError as exc:
            raise ValueError(
                f"Invalid trading session '{value}'. Expected format HH:MM-HH:MM."
            ) from exc
        sessions.append(
            TradingSessionWindow(
                start=_parse_time(raw_start.strip()),
                end=_parse_time(raw_end.strip()),
            )
        )
    return tuple(sessions)


def _parse_time(raw_value: str) -> time:
    try:
        hour, minute = raw_value.split(':', maxsplit=1)
        return time(hour=int(hour), minute=int(minute))
    except ValueError as exc:
        raise ValueError(
            f"Invalid trading session time '{raw_value}'. Expected format HH:MM."
        ) from exc
