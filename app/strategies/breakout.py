from collections import deque

from app.market.models import MarketSnapshot
from app.strategies.signals import Signal


class BreakoutStrategy:
    """Simple intraday breakout skeleton.

    v1 idea:
    - Keep recent prices.
    - Buy when current price breaks above the previous range high.
    - Stay flat otherwise.
    """

    def __init__(self, lookback: int = 12, min_breakout_percent: float = 0.05):
        self.lookback = lookback
        self.min_breakout_percent = min_breakout_percent
        self.prices: deque[float] = deque(maxlen=lookback + 1)

    def on_snapshot(self, snapshot: MarketSnapshot) -> Signal:
        self.prices.append(snapshot.last)

        if len(self.prices) < self.lookback + 1:
            return Signal.hold('warming_up')

        current_price = self.prices[-1]
        previous_prices = list(self.prices)[:-1]
        range_high = max(previous_prices)
        breakout_threshold = range_high * (1 + self.min_breakout_percent / 100)

        if current_price > breakout_threshold:
            return Signal(action='BUY', confidence=0.65, reason='breakout_above_recent_range')

        return Signal.hold('inside_recent_range')
