from collections import deque
from dataclasses import dataclass

from app.market.models import Candle
from app.strategies.signals import Signal


@dataclass(frozen=True)
class BreakoutStrategyConfig:
    lookback: int = 3
    min_breakout_percent: float = 0.05
    require_green_candle: bool = True
    min_close_position_percent: float = 70.0
    min_candle_range_percent: float = 0.05


class BreakoutStrategy:
    """Candle-based intraday breakout strategy.

    Rule:
    - Keep recent closed candles.
    - Wait until enough candles are available.
    - Buy when the latest candle close breaks above the previous range high.
    - Confirm that the breakout candle has enough strength.
    - Stay flat otherwise.
    """

    def __init__(self, config: BreakoutStrategyConfig | None = None):
        self.config = config or BreakoutStrategyConfig()

        if self.config.lookback <= 0:
            raise ValueError('lookback must be greater than 0')

        if self.config.min_breakout_percent < 0:
            raise ValueError('min_breakout_percent must be greater than or equal to 0')

        if not 0 <= self.config.min_close_position_percent <= 100:
            raise ValueError('min_close_position_percent must be between 0 and 100')

        if self.config.min_candle_range_percent < 0:
            raise ValueError('min_candle_range_percent must be greater than or equal to 0')

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

        if current_candle.close <= breakout_threshold:
            return Signal.hold('candle_inside_recent_range')

        strength_rejection_reason = self._breakout_strength_rejection_reason(
            current_candle
        )
        if strength_rejection_reason is not None:
            return Signal.hold(strength_rejection_reason)

        return Signal(
            action='BUY',
            confidence=0.7,
            reason='confirmed_candle_breakout_above_recent_range',
        )

    def _breakout_strength_rejection_reason(self, candle: Candle) -> str | None:
        if self.config.require_green_candle and candle.close <= candle.open:
            return 'breakout_candle_not_green'

        candle_range = candle.high - candle.low
        if candle_range <= 0:
            return 'breakout_candle_has_no_range'

        candle_range_percent = (candle_range / candle.open) * 100
        if candle_range_percent < self.config.min_candle_range_percent:
            return 'breakout_candle_range_too_small'

        close_position_percent = ((candle.close - candle.low) / candle_range) * 100
        if close_position_percent < self.config.min_close_position_percent:
            return 'breakout_close_not_near_high'

        return None