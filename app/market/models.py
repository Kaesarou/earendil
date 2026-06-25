from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    bid: float
    ask: float
    last: float
    timestamp: datetime

    @classmethod
    def now(cls, symbol: str, bid: float, ask: float, last: float) -> 'MarketSnapshot':
        return cls(symbol=symbol, bid=bid, ask=ask, last=last, timestamp=datetime.now(timezone.utc))
    
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
