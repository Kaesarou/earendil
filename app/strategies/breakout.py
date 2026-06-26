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
    require_uptrend: bool = False
    trend_fast_lookback: int = 5
    trend_slow_lookback: int = 15


class BreakoutStrategy:
    """Candle-based intraday breakout strategy.

    Rule:
    - Keep recent closed candles.
    - Wait until enough candles are available.
    - Buy when the latest candle close breaks above the previous range high.
    - Confirm that the breakout candle has enough strength.
    - Optionally require a short-term uptrend.
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

        if self.config.trend_fast_lookback <= 0:
            raise ValueError('trend_fast_lookback must be greater than 0')

        if self.config.trend_slow_lookback <= 0:
            raise ValueError('trend_slow_lookback must be greater than 0')

        if self.config.trend_fast_lookback >= self.config.trend_slow_lookback:
            raise ValueError('trend_fast_lookback must be lower than trend_slow_lookback')

        max_candles = max(
            self.config.lookback + 1,
            self.config.trend_slow_lookback,
        )
        self.candles: deque[Candle] = deque(maxlen=max_candles)

    def on_candle(self, candle: Candle) -> Signal:
        self.candles.append(candle)

        required_candles = self._required_candles()
        if len(self.candles) < required_candles:
            return Signal.hold('warming_up_candles')

        current_candle = self.candles[-1]
        previous_candles = list(self.candles)[-(self.config.lookback + 1):-1]

        range_high = max(previous_candle.high for previous_candle in previous_candles)
        breakout_threshold = range_high * (
            1 + self.config.min_breakout_percent / 100
        )

        if current_candle.close <= breakout_threshold:
            return Signal.hold('candle_inside_recent_range')

        trend_rejection_reason = self._trend_rejection_reason()
        if trend_rejection_reason is not None:
            return Signal.hold(trend_rejection_reason)

        strength_rejection_reason = self._breakout_strength_rejection_reason(
            current_candle
        )
        if strength_rejection_reason is not None:
            return Signal.hold(strength_rejection_reason)

        return Signal(
            action='BUY',
            confidence=0.75 if self.config.require_uptrend else 0.7,
            reason='confirmed_candle_breakout_above_recent_range',
        )

    def _required_candles(self) -> int:
        if not self.config.require_uptrend:
            return self.config.lookback + 1

        return max(
            self.config.lookback + 1,
            self.config.trend_slow_lookback,
        )

    def _trend_rejection_reason(self) -> str | None:
        if not self.config.require_uptrend:
            return None

        closes = [candle.close for candle in self.candles]

        fast_ma = self._average(closes[-self.config.trend_fast_lookback:])
        slow_ma = self._average(closes[-self.config.trend_slow_lookback:])

        if fast_ma <= slow_ma:
            return 'trend_filter_not_confirmed'

        return None

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

    def _average(self, values: list[float]) -> float:
        if not values:
            raise ValueError('Cannot calculate average from empty values')

        return sum(values) / len(values)