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
    atr_lookback: int = 14
    market_regime_filter_enabled: bool = False
    market_regime_min_trend_strength_percent: float = 0.02
    market_regime_min_atr_percent: float = 0.0
    market_regime_max_atr_percent: float = 0.0
    market_regime_max_noise_ratio: float = 0.0


class IntradayTrendStrategy:
    """Intraday trend-following strategy with long and short setups.

    Rule:
    - First determine the session direction.
    - If the symbol is strong, look only for long breakouts.
    - If the symbol is weak, look only for short breakdowns.
    - Stay flat when the context is neutral, noisy, dead, or contradictory.
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
        if self.config.atr_lookback <= 0:
            raise ValueError('atr_lookback must be greater than 0')
        if self.config.min_session_move_percent < 0:
            raise ValueError('min_session_move_percent must be greater than or equal to 0')
        if self.config.min_breakout_percent < 0:
            raise ValueError('min_breakout_percent must be greater than or equal to 0')
        if self.config.min_candle_range_percent < 0:
            raise ValueError('min_candle_range_percent must be greater than or equal to 0')
        if not 0 <= self.config.min_close_position_percent <= 100:
            raise ValueError('min_close_position_percent must be between 0 and 100')
        if self.config.market_regime_min_trend_strength_percent < 0:
            raise ValueError('market_regime_min_trend_strength_percent must be greater than or equal to 0')
        if self.config.market_regime_min_atr_percent < 0:
            raise ValueError('market_regime_min_atr_percent must be greater than or equal to 0')
        if self.config.market_regime_max_atr_percent < 0:
            raise ValueError('market_regime_max_atr_percent must be greater than or equal to 0')
        if self.config.market_regime_max_noise_ratio < 0:
            raise ValueError('market_regime_max_noise_ratio must be greater than or equal to 0')

        max_candles = max(
            self.config.lookback + 1,
            self.config.slow_lookback,
            self.config.session_lookback + 1,
            self.config.atr_lookback + 1,
        )
        self.candles: deque[Candle] = deque(maxlen=max_candles)

    def on_candle(self, candle: Candle) -> Signal:
        self.candles.append(candle)

        if len(self.candles) < self._required_candles():
            return Signal.hold('warming_up_candles')

        session_move_percent = self._session_move_percent()
        regime_metadata = self._market_regime_metadata(session_move_percent)

        if (
            self.config.market_regime_filter_enabled
            and regime_metadata['market_regime'] != 'TRENDING'
        ):
            reason = f"market_regime_{str(regime_metadata['market_regime']).lower()}"
            return Signal.hold(reason, metadata=regime_metadata)

        if session_move_percent >= self.config.min_session_move_percent:
            return self._evaluate_long_setup(session_move_percent, regime_metadata)

        if session_move_percent <= -self.config.min_session_move_percent:
            return self._evaluate_short_setup(session_move_percent, regime_metadata)

        return Signal.hold('session_trend_neutral', metadata=regime_metadata)

    def _evaluate_long_setup(
        self,
        session_move_percent: float,
        regime_metadata: dict[str, float | str],
    ) -> Signal:
        fast_ma, slow_ma = self._moving_averages()

        if fast_ma <= slow_ma:
            return Signal.hold('bullish_trend_not_confirmed', metadata=regime_metadata)

        current_candle = self.candles[-1]
        previous_candles = self._previous_range_candles()

        range_high = max(previous_candle.high for previous_candle in previous_candles)
        breakout_threshold = range_high * (
            1 + self.config.min_breakout_percent / 100
        )

        if current_candle.close <= breakout_threshold:
            return Signal.hold('bullish_breakout_not_confirmed', metadata=regime_metadata)

        rejection_reason = self._long_candle_rejection_reason(current_candle)
        if rejection_reason is not None:
            return Signal.hold(rejection_reason, metadata=regime_metadata)

        trend_strength_percent = self._trend_strength_percent(fast_ma, slow_ma)
        breakout_percent = ((current_candle.close - range_high) / range_high) * 100
        candle_range_percent = self._candle_range_percent(current_candle)
        close_position_percent = self._close_position_percent(current_candle)
        atr_percent = self._atr_percent()

        return Signal(
            action='BUY',
            confidence=0.8,
            reason='intraday_bullish_breakout',
            metadata={
                **regime_metadata,
                'session_move_percent': round(session_move_percent, 4),
                'trend_strength_percent': round(trend_strength_percent, 4),
                'breakout_percent': round(breakout_percent, 4),
                'candle_range_percent': round(candle_range_percent, 4),
                'close_position_percent': round(close_position_percent, 4),
                'atr_percent': round(atr_percent, 4),
                'fast_ma': round(fast_ma, 5),
                'slow_ma': round(slow_ma, 5),
                'range_high': round(range_high, 5),
            },
        )

    def _evaluate_short_setup(
        self,
        session_move_percent: float,
        regime_metadata: dict[str, float | str],
    ) -> Signal:

        fast_ma, slow_ma = self._moving_averages()

        if fast_ma >= slow_ma:
            return Signal.hold('bearish_trend_not_confirmed', metadata=regime_metadata)

        current_candle = self.candles[-1]
        previous_candles = self._previous_range_candles()

        range_low = min(previous_candle.low for previous_candle in previous_candles)
        breakdown_threshold = range_low * (
            1 - self.config.min_breakout_percent / 100
        )

        if current_candle.close >= breakdown_threshold:
            return Signal.hold('bearish_breakdown_not_confirmed', metadata=regime_metadata)

        rejection_reason = self._short_candle_rejection_reason(current_candle)
        if rejection_reason is not None:
            return Signal.hold(rejection_reason, metadata=regime_metadata)

        trend_strength_percent = self._trend_strength_percent(fast_ma, slow_ma)
        breakdown_percent = ((range_low - current_candle.close) / range_low) * 100
        candle_range_percent = self._candle_range_percent(current_candle)
        close_position_percent = self._close_position_percent(current_candle)
        atr_percent = self._atr_percent()

        return Signal(
            action='SELL',
            confidence=0.8,
            reason='intraday_bearish_breakdown',
            metadata={
                **regime_metadata,
                'session_move_percent': round(session_move_percent, 4),
                'trend_strength_percent': round(trend_strength_percent, 4),
                'breakdown_percent': round(breakdown_percent, 4),
                'candle_range_percent': round(candle_range_percent, 4),
                'close_position_percent': round(close_position_percent, 4),
                'atr_percent': round(atr_percent, 4),
                'fast_ma': round(fast_ma, 5),
                'slow_ma': round(slow_ma, 5),
                'range_low': round(range_low, 5),
            },
        )

    def _required_candles(self) -> int:
        return max(
            self.config.lookback + 1,
            self.config.slow_lookback,
            self.config.session_lookback + 1,
            self.config.atr_lookback + 1,
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

    def _market_regime_metadata(self, session_move_percent: float) -> dict[str, float | str]:
        fast_ma, slow_ma = self._moving_averages()
        trend_strength_percent = self._trend_strength_percent(fast_ma, slow_ma)
        atr_percent = self._atr_percent()
        abs_session_move_percent = abs(session_move_percent)
        abs_trend_strength_percent = abs(trend_strength_percent)
        noise_ratio = self._noise_ratio(
            atr_percent=atr_percent,
            session_move_percent=session_move_percent,
        )

        market_regime = self._market_regime(
            abs_session_move_percent=abs_session_move_percent,
            abs_trend_strength_percent=abs_trend_strength_percent,
            atr_percent=atr_percent,
            noise_ratio=noise_ratio,
        )

        return {
            'market_regime': market_regime,
            'regime_session_move_percent': round(session_move_percent, 4),
            'regime_trend_strength_percent': round(trend_strength_percent, 4),
            'regime_atr_percent': round(atr_percent, 4),
            'regime_noise_ratio': round(noise_ratio, 4),
        }

    def _market_regime(
        self,
        abs_session_move_percent: float,
        abs_trend_strength_percent: float,
        atr_percent: float,
        noise_ratio: float,
    ) -> str:
        if abs_session_move_percent < self.config.min_session_move_percent:
            return 'DEAD_MARKET'

        if (
            self.config.market_regime_min_atr_percent > 0
            and atr_percent < self.config.market_regime_min_atr_percent
        ):
            return 'DEAD_MARKET'

        if (
            self.config.market_regime_max_atr_percent > 0
            and atr_percent > self.config.market_regime_max_atr_percent
        ):
            return 'VOLATILE_NOISY'

        if (
            self.config.market_regime_min_trend_strength_percent > 0
            and abs_trend_strength_percent < self.config.market_regime_min_trend_strength_percent
        ):
            return 'RANGING'

        if (
            self.config.market_regime_max_noise_ratio > 0
            and noise_ratio > self.config.market_regime_max_noise_ratio
        ):
            return 'VOLATILE_NOISY'

        return 'TRENDING'

    def _noise_ratio(self, atr_percent: float, session_move_percent: float) -> float:
        abs_session_move_percent = abs(session_move_percent)

        if abs_session_move_percent <= 0:
            return 999999.0

        return atr_percent / abs_session_move_percent

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

        candle_range_percent = self._candle_range_percent(candle)
        if candle_range_percent < self.config.min_candle_range_percent:
            return 'candle_range_too_small'

        close_position_percent = self._close_position_percent(candle)
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

        candle_range_percent = self._candle_range_percent(candle)
        if candle_range_percent < self.config.min_candle_range_percent:
            return 'candle_range_too_small'

        close_position_percent = self._close_position_percent(candle)
        max_close_position_for_short = 100 - self.config.min_close_position_percent

        if close_position_percent > max_close_position_for_short:
            return 'short_close_not_near_low'

        return None

    def _candle_range_percent(self, candle: Candle) -> float:
        if candle.open <= 0:
            raise ValueError(f'Cannot calculate candle range with invalid open={candle.open}')

        return ((candle.high - candle.low) / candle.open) * 100

    def _close_position_percent(self, candle: Candle) -> float:
        candle_range = candle.high - candle.low

        if candle_range <= 0:
            raise ValueError('Cannot calculate close position from candle without range')

        return ((candle.close - candle.low) / candle_range) * 100

    def _trend_strength_percent(self, fast_ma: float, slow_ma: float) -> float:
        if slow_ma <= 0:
            raise ValueError(f'Cannot calculate trend strength with invalid slow_ma={slow_ma}')

        return ((fast_ma - slow_ma) / slow_ma) * 100

    def _atr_percent(self) -> float:
        candles = list(self.candles)
        current_close = candles[-1].close

        if current_close <= 0:
            raise ValueError(f'Cannot calculate ATR percent with invalid close={current_close}')

        true_ranges: list[float] = []
        atr_candles = candles[-(self.config.atr_lookback + 1):]

        for index in range(1, len(atr_candles)):
            candle = atr_candles[index]
            previous_close = atr_candles[index - 1].close
            true_range = max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
            true_ranges.append(true_range)

        if not true_ranges:
            raise ValueError('Cannot calculate ATR without true ranges')

        atr = self._average(true_ranges)
        return (atr / current_close) * 100

    def _average(self, values: list[float]) -> float:
        if not values:
            raise ValueError('Cannot calculate average from empty values')

        return sum(values) / len(values)
