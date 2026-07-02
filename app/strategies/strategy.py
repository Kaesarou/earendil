from collections import deque
from datetime import timedelta

from app.market.models import Candle, MarketSnapshot
from app.strategies.aggressive_strategy import AggressiveStrategyConfig
from app.strategies.balanced_strategy import BalancedStrategyConfig
from app.strategies.models import StrategyProfileConfig, TrendStrategyConfig
from app.strategies.signals import Signal

StrategyMetadata = dict[str, float | int | str | bool]

SNAPSHOT_HISTORY_MAXLEN = 512


def strategy_profile_from_name(name: str) -> StrategyProfileConfig:
    normalized_name = name.strip().lower()
    if normalized_name in ('balanced', 'balance'):
        return BalancedStrategyConfig()
    if normalized_name in ('aggressive', 'aggressif', 'aggressiv'):
        return AggressiveStrategyConfig()
    raise ValueError(
        f'Unsupported strategy aggressiveness: {name}. '
        'Expected one of: balanced, aggressive.'
    )


class TrendStrategy:
    """Trend-following strategy with long and short setups.

    Rule:
    - First determine the session direction.
    - If the symbol is strong, look only for long breakouts.
    - If the symbol is weak, look only for short breakdowns.
    - Stay flat when the context is neutral, noisy, dead, or contradictory.
    """

    def __init__(self, config: TrendStrategyConfig):
        self.config = config

        max_candles = max(
            self.config.lookback + 1,
            self.config.slow_lookback,
            self.config.session_lookback + 1,
            self.config.atr_lookback + 1,
        )
        self.candles: deque[Candle] = deque(maxlen=max_candles)
        self.snapshots: deque[MarketSnapshot] = deque(maxlen=SNAPSHOT_HISTORY_MAXLEN)

    def on_snapshot(self, snapshot: MarketSnapshot) -> None:
        self.snapshots.append(snapshot)

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
        regime_metadata: StrategyMetadata,
    ) -> Signal:
        fast_ma, slow_ma = self._moving_averages()

        if fast_ma <= slow_ma:
            return Signal.hold('bullish_trend_not_confirmed', metadata=regime_metadata)

        current_candle = self.candles[-1]
        setup_metadata = {
            **regime_metadata,
            **self._candle_reliability_metadata(current_candle),
        }
        previous_candles = self._previous_range_candles()
        range_high = max(previous_candle.high for previous_candle in previous_candles)

        if setup_metadata['candle_reliable'] is False:
            return self._evaluate_long_snapshot_momentum_fallback(
                session_move_percent=session_move_percent,
                fast_ma=fast_ma,
                slow_ma=slow_ma,
                range_high=range_high,
                setup_metadata=setup_metadata,
            )

        breakout_threshold = range_high * (
            1 + self.config.min_breakout_percent / 100
        )

        if current_candle.close <= breakout_threshold:
            return Signal.hold('bullish_breakout_not_confirmed', metadata=setup_metadata)

        rejection_reason = self._long_candle_rejection_reason(current_candle)
        if rejection_reason is not None:
            return Signal.hold(rejection_reason, metadata=setup_metadata)

        confirmed, reason, snapshot_metadata = self._snapshot_momentum_confirmation(
            side='long',
            mode='entry_confirmation',
        )
        entry_metadata = {
            **setup_metadata,
            **snapshot_metadata,
            'entry_confirmation_source': 'candle_and_snapshot_momentum',
        }

        if not confirmed:
            return Signal.hold(reason, metadata=entry_metadata)

        trend_strength_percent = self._trend_strength_percent(fast_ma, slow_ma)
        breakout_percent = ((current_candle.close - range_high) / range_high) * 100
        candle_range_percent = self._candle_range_percent(current_candle)
        close_position_percent = self._close_position_percent(current_candle)
        atr_percent = self._atr_percent()

        return Signal(
            action='BUY',
            confidence=0.8,
            reason='trend_bullish_breakout',
            metadata={
                **entry_metadata,
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
        regime_metadata: StrategyMetadata,
    ) -> Signal:
        fast_ma, slow_ma = self._moving_averages()

        if fast_ma >= slow_ma:
            return Signal.hold('bearish_trend_not_confirmed', metadata=regime_metadata)

        current_candle = self.candles[-1]
        setup_metadata = {
            **regime_metadata,
            **self._candle_reliability_metadata(current_candle),
        }
        previous_candles = self._previous_range_candles()
        range_low = min(previous_candle.low for previous_candle in previous_candles)

        if setup_metadata['candle_reliable'] is False:
            return self._evaluate_short_snapshot_momentum_fallback(
                session_move_percent=session_move_percent,
                fast_ma=fast_ma,
                slow_ma=slow_ma,
                range_low=range_low,
                setup_metadata=setup_metadata,
            )

        breakdown_threshold = range_low * (
            1 - self.config.min_breakout_percent / 100
        )

        if current_candle.close >= breakdown_threshold:
            return Signal.hold('bearish_breakdown_not_confirmed', metadata=setup_metadata)

        rejection_reason = self._short_candle_rejection_reason(current_candle)
        if rejection_reason is not None:
            return Signal.hold(rejection_reason, metadata=setup_metadata)

        confirmed, reason, snapshot_metadata = self._snapshot_momentum_confirmation(
            side='short',
            mode='entry_confirmation',
        )
        entry_metadata = {
            **setup_metadata,
            **snapshot_metadata,
            'entry_confirmation_source': 'candle_and_snapshot_momentum',
        }

        if not confirmed:
            return Signal.hold(reason, metadata=entry_metadata)

        trend_strength_percent = self._trend_strength_percent(fast_ma, slow_ma)
        breakdown_percent = ((range_low - current_candle.close) / range_low) * 100
        candle_range_percent = self._candle_range_percent(current_candle)
        close_position_percent = self._close_position_percent(current_candle)
        atr_percent = self._atr_percent()

        return Signal(
            action='SELL',
            confidence=0.8,
            reason='trend_bearish_breakdown',
            metadata={
                **entry_metadata,
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

    def _evaluate_long_snapshot_momentum_fallback(
        self,
        session_move_percent: float,
        fast_ma: float,
        slow_ma: float,
        range_high: float,
        setup_metadata: StrategyMetadata,
    ) -> Signal:
        confirmed, reason, snapshot_metadata = self._snapshot_momentum_confirmation(
            side='long',
            mode='fallback',
        )
        fallback_metadata = {
            **setup_metadata,
            **snapshot_metadata,
        }

        if not confirmed:
            return Signal.hold(reason, metadata=fallback_metadata)

        return self._build_long_snapshot_momentum_signal(
            session_move_percent=session_move_percent,
            fast_ma=fast_ma,
            slow_ma=slow_ma,
            range_high=range_high,
            setup_metadata=setup_metadata,
            snapshot_metadata=snapshot_metadata,
        )

    def _evaluate_short_snapshot_momentum_fallback(
        self,
        session_move_percent: float,
        fast_ma: float,
        slow_ma: float,
        range_low: float,
        setup_metadata: StrategyMetadata,
    ) -> Signal:
        confirmed, reason, snapshot_metadata = self._snapshot_momentum_confirmation(
            side='short',
            mode='fallback',
        )
        fallback_metadata = {
            **setup_metadata,
            **snapshot_metadata,
        }

        if not confirmed:
            return Signal.hold(reason, metadata=fallback_metadata)

        return self._build_short_snapshot_momentum_signal(
            session_move_percent=session_move_percent,
            fast_ma=fast_ma,
            slow_ma=slow_ma,
            range_low=range_low,
            setup_metadata=setup_metadata,
            snapshot_metadata=snapshot_metadata,
        )

    def _build_long_snapshot_momentum_signal(
        self,
        session_move_percent: float,
        fast_ma: float,
        slow_ma: float,
        range_high: float,
        setup_metadata: StrategyMetadata,
        snapshot_metadata: StrategyMetadata,
    ) -> Signal:
        trend_strength_percent = self._trend_strength_percent(fast_ma, slow_ma)
        atr_percent = self._atr_percent()

        return Signal(
            action='BUY',
            confidence=0.75,
            reason='trend_bullish_snapshot_momentum',
            metadata={
                **setup_metadata,
                **snapshot_metadata,
                'session_move_percent': round(session_move_percent, 4),
                'trend_strength_percent': round(trend_strength_percent, 4),
                'breakout_percent': snapshot_metadata.get('snapshot_breakout_percent', 0.0),
                'candle_range_percent': snapshot_metadata.get('snapshot_range_percent', 0.0),
                'close_position_percent': snapshot_metadata.get(
                    'snapshot_close_position_percent',
                    0.0,
                ),
                'atr_percent': round(atr_percent, 4),
                'fast_ma': round(fast_ma, 5),
                'slow_ma': round(slow_ma, 5),
                'range_high': round(range_high, 5),
                'confirmation_source': 'snapshot_momentum',
            },
        )

    def _build_short_snapshot_momentum_signal(
        self,
        session_move_percent: float,
        fast_ma: float,
        slow_ma: float,
        range_low: float,
        setup_metadata: StrategyMetadata,
        snapshot_metadata: StrategyMetadata,
    ) -> Signal:
        trend_strength_percent = self._trend_strength_percent(fast_ma, slow_ma)
        atr_percent = self._atr_percent()

        return Signal(
            action='SELL',
            confidence=0.75,
            reason='trend_bearish_snapshot_momentum',
            metadata={
                **setup_metadata,
                **snapshot_metadata,
                'session_move_percent': round(session_move_percent, 4),
                'trend_strength_percent': round(trend_strength_percent, 4),
                'breakdown_percent': snapshot_metadata.get('snapshot_breakdown_percent', 0.0),
                'candle_range_percent': snapshot_metadata.get('snapshot_range_percent', 0.0),
                'close_position_percent': snapshot_metadata.get(
                    'snapshot_close_position_percent',
                    100.0,
                ),
                'atr_percent': round(atr_percent, 4),
                'fast_ma': round(fast_ma, 5),
                'slow_ma': round(slow_ma, 5),
                'range_low': round(range_low, 5),
                'confirmation_source': 'snapshot_momentum',
            },
        )

    def _snapshot_momentum_confirmation(
        self,
        side: str,
        mode: str = 'fallback',
    ) -> tuple[bool, str, StrategyMetadata]:
        window_snapshots = self._snapshot_window_snapshots()
        rejection_reason = self._snapshot_momentum_rejection_reason(side)

        if len(window_snapshots) < 2:
            current_snapshot = self.snapshots[-1] if self.snapshots else None
            metadata: StrategyMetadata = {
                'snapshot_momentum_confirmed': False,
                'snapshot_momentum_side': side,
                'snapshot_momentum_window_seconds': self.config.snapshot_momentum_window_seconds,
                'snapshot_count': len(self.snapshots),
                'snapshot_momentum_rejection_detail': 'snapshot_momentum_not_enough_time_window',
            }

            if current_snapshot is not None:
                metadata['snapshot_current_price'] = round(current_snapshot.last, 5)

            return False, rejection_reason, metadata

        prices = [snapshot.last for snapshot in window_snapshots]
        reference_price = prices[0]
        current_price = prices[-1]

        if reference_price <= 0 or current_price <= 0:
            return (
                False,
                rejection_reason,
                {
                    'snapshot_momentum_confirmed': False,
                    'snapshot_momentum_side': side,
                    'snapshot_momentum_window_seconds': self.config.snapshot_momentum_window_seconds,
                    'snapshot_reference_price': round(reference_price, 5),
                    'snapshot_current_price': round(current_price, 5),
                    'snapshot_momentum_rejection_detail': 'snapshot_momentum_invalid_price',
                },
            )

        previous_prices = prices[:-1]
        if any(price <= 0 for price in previous_prices):
            return (
                False,
                rejection_reason,
                {
                    'snapshot_momentum_confirmed': False,
                    'snapshot_momentum_side': side,
                    'snapshot_momentum_window_seconds': self.config.snapshot_momentum_window_seconds,
                    'snapshot_reference_price': round(reference_price, 5),
                    'snapshot_current_price': round(current_price, 5),
                    'snapshot_momentum_rejection_detail': 'snapshot_momentum_invalid_price',
                },
            )

        momentum_percent = ((current_price - reference_price) / reference_price) * 100
        snapshot_range_percent = self._snapshot_range_percent(prices, reference_price)
        snapshot_close_position_percent = self._snapshot_close_position_percent(prices)

        if side == 'long':
            snapshot_range_high = max(previous_prices)
            breakout_percent = ((current_price - snapshot_range_high) / snapshot_range_high) * 100
            confirmed = momentum_percent >= self.config.min_snapshot_momentum_percent

            if mode == 'fallback':
                confirmed = (
                    confirmed
                    and breakout_percent >= self.config.min_breakout_percent
                )

            reason = (
                'snapshot_momentum_confirmed'
                if confirmed
                else rejection_reason
            )

            return (
                confirmed,
                reason,
                {
                    'snapshot_momentum_confirmed': confirmed,
                    'snapshot_momentum_side': side,
                    'snapshot_momentum_percent': round(momentum_percent, 4),
                    'snapshot_momentum_window_seconds': self.config.snapshot_momentum_window_seconds,
                    'snapshot_momentum_required_percent': round(
                        self.config.min_snapshot_momentum_percent,
                        4,
                    ),
                    'snapshot_breakout_percent': round(breakout_percent, 4),
                    'snapshot_range_percent': round(snapshot_range_percent, 4),
                    'snapshot_close_position_percent': round(snapshot_close_position_percent, 4),
                    'snapshot_reference_price': round(reference_price, 5),
                    'snapshot_current_price': round(current_price, 5),
                    'snapshot_range_high': round(snapshot_range_high, 5),
                    'confirmation_source': 'snapshot_momentum',
                },
            )

        if side == 'short':
            snapshot_range_low = min(previous_prices)
            breakdown_percent = ((snapshot_range_low - current_price) / snapshot_range_low) * 100
            confirmed = momentum_percent <= -self.config.min_snapshot_momentum_percent

            if mode == 'fallback':
                confirmed = (
                    confirmed
                    and breakdown_percent >= self.config.min_breakout_percent
                )

            reason = (
                'snapshot_momentum_confirmed'
                if confirmed
                else rejection_reason
            )

            return (
                confirmed,
                reason,
                {
                    'snapshot_momentum_confirmed': confirmed,
                    'snapshot_momentum_side': side,
                    'snapshot_momentum_percent': round(momentum_percent, 4),
                    'snapshot_momentum_window_seconds': self.config.snapshot_momentum_window_seconds,
                    'snapshot_momentum_required_percent': round(
                        self.config.min_snapshot_momentum_percent,
                        4,
                    ),
                    'snapshot_breakdown_percent': round(breakdown_percent, 4),
                    'snapshot_range_percent': round(snapshot_range_percent, 4),
                    'snapshot_close_position_percent': round(snapshot_close_position_percent, 4),
                    'snapshot_reference_price': round(reference_price, 5),
                    'snapshot_current_price': round(current_price, 5),
                    'snapshot_range_low': round(snapshot_range_low, 5),
                    'confirmation_source': 'snapshot_momentum',
                },
            )

        return (
            False,
            'snapshot_momentum_invalid_side',
            {
                'snapshot_momentum_confirmed': False,
                'snapshot_momentum_side': side,
                'snapshot_momentum_window_seconds': self.config.snapshot_momentum_window_seconds,
            },
        )

    def _snapshot_window_snapshots(self) -> list[MarketSnapshot]:
        if not self.snapshots:
            return []

        snapshots = list(self.snapshots)
        current_snapshot = snapshots[-1]
        target_timestamp = current_snapshot.timestamp - timedelta(
            seconds=self.config.snapshot_momentum_window_seconds,
        )

        reference_snapshot: MarketSnapshot | None = None
        for snapshot in snapshots:
            if snapshot.timestamp <= target_timestamp:
                reference_snapshot = snapshot
            else:
                break

        if reference_snapshot is None:
            return []

        return [
            snapshot
            for snapshot in snapshots
            if reference_snapshot.timestamp <= snapshot.timestamp <= current_snapshot.timestamp
        ]

    def _snapshot_momentum_rejection_reason(self, side: str) -> str:
        if side == 'long':
            return 'snapshot_bullish_momentum_not_confirmed'

        if side == 'short':
            return 'snapshot_bearish_momentum_not_confirmed'

        return 'snapshot_momentum_invalid_side'

    def _snapshot_range_percent(self, prices: list[float], reference_price: float) -> float:
        if reference_price <= 0:
            return 0.0

        snapshot_range = max(prices) - min(prices)
        return (snapshot_range / reference_price) * 100

    def _snapshot_close_position_percent(self, prices: list[float]) -> float:
        snapshot_range = max(prices) - min(prices)

        if snapshot_range <= 0:
            return 50.0

        current_price = prices[-1]
        return ((current_price - min(prices)) / snapshot_range) * 100

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

    def _market_regime_metadata(self, session_move_percent: float) -> StrategyMetadata:
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
        unreliable_reason = self._unreliable_candle_reason(candle)
        if unreliable_reason is not None:
            return unreliable_reason

        if candle.close <= candle.open:
            return 'long_candle_not_green'

        candle_range_percent = self._candle_range_percent(candle)
        if candle_range_percent < self.config.min_candle_range_percent:
            return 'candle_range_too_small'

        close_position_percent = self._close_position_percent(candle)
        if close_position_percent < self.config.min_close_position_percent:
            return 'long_close_not_near_high'

        return None

    def _short_candle_rejection_reason(self, candle: Candle) -> str | None:
        unreliable_reason = self._unreliable_candle_reason(candle)
        if unreliable_reason is not None:
            return unreliable_reason

        if candle.close >= candle.open:
            return 'short_candle_not_red'

        candle_range_percent = self._candle_range_percent(candle)
        if candle_range_percent < self.config.min_candle_range_percent:
            return 'candle_range_too_small'

        close_position_percent = self._close_position_percent(candle)
        max_close_position_for_short = 100 - self.config.min_close_position_percent

        if close_position_percent > max_close_position_for_short:
            return 'short_close_not_near_low'

        return None

    def _candle_reliability_metadata(self, candle: Candle) -> StrategyMetadata:
        unreliable_reason = self._unreliable_candle_reason(candle)
        return {
            'candle_reliable': unreliable_reason is None,
            'candle_unreliable_reason': unreliable_reason or '',
        }

    def _unreliable_candle_reason(self, candle: Candle) -> str | None:
        if candle.open <= 0:
            return 'invalid_candle_open'

        if candle.high < candle.low:
            return 'invalid_candle_range'

        if (
            candle.open == candle.high
            and candle.high == candle.low
            and candle.low == candle.close
        ):
            return 'flat_candle_ohlc'

        if candle.high == candle.low:
            return 'candle_has_no_range'

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
