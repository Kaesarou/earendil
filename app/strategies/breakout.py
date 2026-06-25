from collections import deque
from dataclasses import dataclass

from app.market.models import Candle
from app.strategies.signals import Signal


@dataclass(frozen=True)
class BreakoutStrategyConfig:
    lookback: int = 3
    min_breakout_percent: float = 0.05


class BreakoutStrategy:
    """Candle-based intraday breakout strategy.

    Rule:
    - Keep recent closed candles.
    - Wait until enough candles are available.
    - Buy when the latest candle close breaks above the previous range high.
    - Stay flat otherwise.
    """

    def __init__(self, config: BreakoutStrategyConfig | None = None):
        self.config = config or BreakoutStrategyConfig()

        if self.config.lookback <= 0:
            raise ValueError('lookback must be greater than 0')

        if self.config.min_breakout_percent < 0:
            raise ValueError('min_breakout_percent must be greater than or equal to 0')

        self.candles: deque[Candle] = deque(maxlen=self.config.lookback + 1)

    def on_candle(self, candle: Candle) -> Signal:
        self.candles.append(candle)

        if len(self.candles) < self.config.lookback + 1:
            return Signal.hold('warming_up_candles')

        current_candle = self.candles[-1]
        previous_candles = list(self.candles)[:-1]

        range_high = max(previous_candle.high for previous_candle in previous_candles)
        breakout_threshold = range_high * (
            1 + self.config.min_breakout_percent / 100
        )

        if current_candle.close > breakout_threshold:
            return Signal(
                action='BUY',
                confidence=0.65,
                reason='candle_breakout_above_recent_range',
            )

        return Signal.hold('candle_inside_recent_range')