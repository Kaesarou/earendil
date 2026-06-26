from collections import deque
from dataclasses import dataclass

from app.market.models import Candle
from app.strategies.signals import Signal


@dataclass(frozen=True)
class IntradayTrendStrategyConfig:
    lookback: int = 3
    fast_lookback: int = 5
    slow_lookback: int = 15
    session_lookback: int = 30
    min_session_move_percent: float = 0.15
    min_breakout_percent: float = 0.05
    min_candle_range_percent: float = 0.04
    min_close_position_percent: float = 70.0
    allow_short: bool = False


class IntradayTrendStrategy:
    """Intraday trend-following strategy with long and short setups.

    Rule:
    - First determine the session direction.
    - If the symbol is strong, look only for long breakouts.
    - If the symbol is weak, look only for short breakdowns.
    - Stay flat when the context is neutral or contradictory.
    """

    def __init__(self, config: IntradayTrendStrategyConfig | None = None):
        self.config = config or IntradayTrendStrategyConfig()

        if self.config.lookback <= 0:
            raise ValueError('lookback must be greater than 0')

        if self.config.fast_lookback <= 0:
            raise ValueError('fast_lookback must be greater than 0')

        if self.config.slow_lookback <= 0:
            raise ValueError('slow_lookback must be greater than 0')

        if self.config.fast_lookback >= self.config.slow_lookback:
            raise ValueError('fast_lookback must be lower than slow_lookback')

        if self.config.session_lookback <= 0:
            raise ValueError('session_lookback must be greater than 0')

        if self.config.min_session_move_percent < 0:
            raise ValueError('min_session_move_percent must be greater than or equal to 0')

        if self.config.min_breakout_percent < 0:
            raise ValueError('min_breakout_percent must be greater than or equal to 0')

        if self.config.min_candle_range_percent < 0:
            raise ValueError('min_candle_range_percent must be greater than or equal to 0')

        if not 0 <= self.config.min_close_position_percent <= 100:
            raise ValueError('min_close_position_percent must be between 0 and 100')

        max_candles = max(
            self.config.lookback + 1,
            self.config.slow_lookback,
            self.config.session_lookback + 1,
        )
        self.candles: deque[Candle] = deque(maxlen=max_candles)

    def on_candle(self, candle: Candle) -> Signal:
        self.candles.append(candle)

        if len(self.candles) < self._required_candles():
            return Signal.hold('warming_up_candles')

        session_move_percent = self._session_move_percent()

        if session_move_percent >= self.config.min_session_move_percent:
            return self._evaluate_long_setup()

        if session_move_percent <= -self.config.min_session_move_percent:
            return self._evaluate_short_setup()

        return Signal.hold('session_trend_neutral')

    def _evaluate_long_setup(self) -> Signal:
        if not self._is_short_term_uptrend():
            return Signal.hold('bullish_trend_not_confirmed')

        current_candle = self.candles[-1]
        previous_candles = self._previous_range_candles()

        range_high = max(previous_candle.high for previous_candle in previous_candles)
        breakout_threshold = range_high * (
            1 + self.config.min_breakout_percent / 100
        )

        if current_candle.close <= breakout_threshold:
            return Signal.hold('bullish_breakout_not_confirmed')

        rejection_reason = self._long_candle_rejection_reason(current_candle)
        if rejection_reason is not None:
            return Signal.hold(rejection_reason)

        return Signal(
            action='BUY',
            confidence=0.8,
            reason='intraday_bullish_breakout',
        )

    def _evaluate_short_setup(self) -> Signal:
        if not self.config.allow_short:
            return Signal.hold('short_signals_disabled_by_strategy')

        if not self._is_short_term_downtrend():
            return Signal.hold('bearish_trend_not_confirmed')

        current_candle = self.candles[-1]
        previous_candles = self._previous_range_candles()

        range_low = min(previous_candle.low for previous_candle in previous_candles)
        breakdown_threshold = range_low * (
            1 - self.config.min_breakout_percent / 100
        )

        if current_candle.close >= breakdown_threshold:
            return Signal.hold('bearish_breakdown_not_confirmed')

        rejection_reason = self._short_candle_rejection_reason(current_candle)
        if rejection_reason is not None:
            return Signal.hold(rejection_reason)

        return Signal(
            action='SELL',
            confidence=0.8,
            reason='intraday_bearish_breakdown',
        )

    def _required_candles(self) -> int:
        return max(
            self.config.lookback + 1,
            self.config.slow_lookback,
            self.config.session_lookback + 1,
        )

    def _session_move_percent(self) -> float:
        candles = list(self.candles)
        current_close = candles[-1].close
        reference_close = candles[-(self.config.session_lookback + 1)].close

        if reference_close <= 0:
            raise ValueError(
                f'Cannot calculate session move with invalid reference_close={reference_close}'
            )

        return ((current_close - reference_close) / reference_close) * 100

    def _is_short_term_uptrend(self) -> bool:
        fast_ma, slow_ma = self._moving_averages()
        return fast_ma > slow_ma

    def _is_short_term_downtrend(self) -> bool:
        fast_ma, slow_ma = self._moving_averages()
        return fast_ma < slow_ma

    def _moving_averages(self) -> tuple[float, float]:
        closes = [candle.close for candle in self.candles]

        fast_ma = self._average(closes[-self.config.fast_lookback:])
        slow_ma = self._average(closes[-self.config.slow_lookback:])

        return fast_ma, slow_ma

    def _previous_range_candles(self) -> list[Candle]:
        candles = list(self.candles)
        return candles[-(self.config.lookback + 1):-1]

    def _long_candle_rejection_reason(self, candle: Candle) -> str | None:
        if candle.close <= candle.open:
            return 'long_candle_not_green'

        candle_range = candle.high - candle.low
        if candle_range <= 0:
            return 'candle_has_no_range'

        if candle.open <= 0:
            return 'invalid_candle_open'

        candle_range_percent = (candle_range / candle.open) * 100
        if candle_range_percent < self.config.min_candle_range_percent:
            return 'candle_range_too_small'

        close_position_percent = ((candle.close - candle.low) / candle_range) * 100
        if close_position_percent < self.config.min_close_position_percent:
            return 'long_close_not_near_high'

        return None

    def _short_candle_rejection_reason(self, candle: Candle) -> str | None:
        if candle.close >= candle.open:
            return 'short_candle_not_red'

        candle_range = candle.high - candle.low
        if candle_range <= 0:
            return 'candle_has_no_range'

        if candle.open <= 0:
            return 'invalid_candle_open'

        candle_range_percent = (candle_range / candle.open) * 100
        if candle_range_percent < self.config.min_candle_range_percent:
            return 'candle_range_too_small'

        close_position_percent = ((candle.close - candle.low) / candle_range) * 100
        max_close_position_for_short = 100 - self.config.min_close_position_percent

        if close_position_percent > max_close_position_for_short:
            return 'short_close_not_near_low'

        return None

    def _average(self, values: list[float]) -> float:
        if not values:
            raise ValueError('Cannot calculate average from empty values')

        return sum(values) / len(values)