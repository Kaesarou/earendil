from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class PriceSource(StrEnum):
    BROKER_LAST = 'broker_last'
    BID_ASK_MIDPOINT = 'bid_ask_midpoint'


class TimestampSource(StrEnum):
    BROKER = 'broker'
    LOCAL_RECEIVE_TIME = 'local_receive_time'


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    bid: float
    ask: float
    last: float
    timestamp: datetime
    received_at: datetime | None = None
    price_source: PriceSource = PriceSource.BROKER_LAST
    timestamp_source: TimestampSource = TimestampSource.BROKER

    def __post_init__(self) -> None:
        timestamp = _as_utc(self.timestamp)
        received_at = _as_utc(self.received_at or timestamp)
        object.__setattr__(self, 'timestamp', timestamp)
        object.__setattr__(self, 'received_at', received_at)
        object.__setattr__(self, 'symbol', self.symbol.strip().upper())

    @classmethod
    def now(
        cls,
        symbol: str,
        bid: float,
        ask: float,
        last: float,
        *,
        price_source: PriceSource = PriceSource.BROKER_LAST,
        timestamp_source: TimestampSource = TimestampSource.LOCAL_RECEIVE_TIME,
    ) -> 'MarketSnapshot':
        now = datetime.now(timezone.utc)
        return cls(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
            timestamp=now,
            received_at=now,
            price_source=price_source,
            timestamp_source=timestamp_source,
        )


@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe_seconds: int
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    opened_at: datetime
    closed_at: datetime


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
