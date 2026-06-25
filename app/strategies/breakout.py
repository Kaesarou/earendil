from collections import deque

from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal


class BreakoutStrategy:
    """Simple candle-based intraday breakout strategy.

    MVP rule:
    - Keep recent closed candles.
    - Wait until enough candles are available.
    - Buy when the latest candle close breaks above the previous range high.
    - Stay flat otherwise.
    """

    def __init__(self, lookback: int = 3, min_breakout_percent: float = 0.05):
        if lookback <= 0:
            raise ValueError('lookback must be greater than 0')

        if min_breakout_percent < 0:
            raise ValueError('min_breakout_percent must be greater than or equal to 0')

        self.lookback = lookback
        self.min_breakout_percent = min_breakout_percent
        self.candles: deque[Candle] = deque(maxlen=lookback + 1)

    def on_candle(self, candle: Candle) -> Signal:
        self.candles.append(candle)

        if len(self.candles) < self.lookback + 1:
            return Signal.hold('warming_up_candles')

        current_candle = self.candles[-1]
        previous_candles = list(self.candles)[:-1]

        range_high = max(candle.high for candle in previous_candles)
        breakout_threshold = range_high * (1 + self.min_breakout_percent / 100)

        if current_candle.close > breakout_threshold:
            return Signal(
                action='BUY',
                confidence=0.65,
                reason='candle_breakout_above_recent_range',
            )

        return Signal.hold('candle_inside_recent_range')

    def on_snapshot(self, snapshot: MarketSnapshot) -> Signal:
        """Deprecated compatibility method.

        Strategies should evaluate closed candles, not raw snapshots.
        Kept temporarily to avoid breaking older tests/callers.
        """
        return Signal.hold('snapshot_strategy_disabled')