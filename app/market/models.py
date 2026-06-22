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
