from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_broker_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith('Z'):
        normalized = f'{normalized[:-1]}+00:00'
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def optional_string(value: object) -> str | None:
    if value is None:
        return None
    parsed = str(value).strip()
    return parsed or None


@dataclass(frozen=True)
class NormalizedRate:
    source: str
    symbol: str
    instrument_id: int
    bid: float
    ask: float
    last: float
    price_source: str
    received_at: datetime
    source_timestamp: datetime | None = None
    message_id: str | None = None
    price_rate_id: str | None = None
    state_reconstructed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dataclass(self)


@dataclass(frozen=True)
class NormalizedCandle:
    source: str
    symbol: str
    instrument_id: int
    interval: str
    opened_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    potentially_incomplete: bool

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dataclass(self)


def _serialize_dataclass(value) -> dict[str, Any]:
    result = asdict(value)
    for key, item in tuple(result.items()):
        if isinstance(item, datetime):
            result[key] = item.isoformat()
    return result
