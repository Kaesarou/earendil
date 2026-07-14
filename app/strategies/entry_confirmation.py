from dataclasses import dataclass

from app.market.models import Candle
from app.strategies.signals import Signal


@dataclass(frozen=True)
class EntryConfirmationConfig:
    max_candles: int = 5
    consecutive_closes: int = 2
    retest_atr_multiplier: float = 0.50
    retest_spread_multiplier: float = 1.00
    retest_candle_range_multiplier: float = 0.25
    min_reward_to_risk: float = 1.0


@dataclass(frozen=True)
class EntryConfirmationDecision:
    state: str
    reason: str
    confirmation_type: str | None = None
    consecutive_closes: int = 0
    retest_extreme_price: float | None = None
    structural_invalidation_price: float | None = None


class EntryConfirmationEvaluator:
    def evaluate(
        self,
        *,
        side: str,
        breakout_level: float,
        previous_state: str,
        previous_consecutive_closes: int,
        previous_retest_extreme_price: float | None,
        previous_structure_extreme_price: float | None,
        candle: Candle,
        signal: Signal,
        spread_percent: float,
        config: EntryConfirmationConfig,
    ) -> EntryConfirmationDecision:
        normalized_side = side.strip().upper()
        if normalized_side not in {'BUY', 'SELL'}:
            return EntryConfirmationDecision('invalidated', 'unsupported_pending_side')
        if signal.action in {'BUY', 'SELL'} and signal.action != normalized_side:
            return EntryConfirmationDecision('invalidated', 'opposite_signal')

        tolerance_percent = self._tolerance_percent(
            candle=candle,
            signal=signal,
            spread_percent=spread_percent,
            config=config,
        )
        tolerance_price = breakout_level * tolerance_percent / 100
        momentum_aligned = self._momentum_aligned(normalized_side, signal)
        if self._structure_invalidated(
            side=normalized_side,
            candle=candle,
            breakout_level=breakout_level,
            tolerance_price=tolerance_price,
        ):
            return EntryConfirmationDecision('invalidated', 'structure_invalidated')
        if self._momentum_inverted(normalized_side, signal):
            return EntryConfirmationDecision('invalidated', 'momentum_inverted')

        structure_extreme = self._updated_structure_extreme(
            side=normalized_side,
            previous=previous_structure_extreme_price,
            candle=candle,
        )
        retest_detected = self._retest_detected(
            side=normalized_side,
            candle=candle,
            breakout_level=breakout_level,
            tolerance_price=tolerance_price,
        )
        retest_extreme = previous_retest_extreme_price
        next_state = previous_state
        if retest_detected:
            retest_extreme = self._updated_retest_extreme(
                side=normalized_side,
                previous=previous_retest_extreme_price,
                candle=candle,
            )
            next_state = 'retest_detected'

        if (
            previous_state == 'retest_detected'
            and signal.action == normalized_side
            and momentum_aligned
            and self._continuation_candle(
                side=normalized_side,
                candle=candle,
                breakout_level=breakout_level,
            )
        ):
            return EntryConfirmationDecision(
                state='confirmed',
                reason='retest_continuation_confirmed',
                confirmation_type='retest_continuation',
                consecutive_closes=previous_consecutive_closes,
                retest_extreme_price=retest_extreme,
                structural_invalidation_price=(
                    retest_extreme if retest_extreme is not None else structure_extreme
                ),
            )

        return EntryConfirmationDecision(
            state=next_state,
            reason='retest_detected' if next_state == 'retest_detected' else 'waiting_for_retest',
            consecutive_closes=0,
            retest_extreme_price=retest_extreme,
            structural_invalidation_price=structure_extreme,
        )

    def _tolerance_percent(
        self,
        *,
        candle: Candle,
        signal: Signal,
        spread_percent: float,
        config: EntryConfirmationConfig,
    ) -> float:
        atr_percent = self._float((signal.metadata or {}).get('atr_percent')) or 0.0
        candle_range_percent = (
            ((candle.high - candle.low) / candle.open) * 100 if candle.open > 0 else 0.0
        )
        return max(
            atr_percent * config.retest_atr_multiplier,
            max(0.0, spread_percent) * config.retest_spread_multiplier,
            candle_range_percent * config.retest_candle_range_multiplier,
        )

    def _momentum_aligned(self, side: str, signal: Signal) -> bool:
        momentum = self._float((signal.metadata or {}).get('snapshot_momentum_percent'))
        if momentum is None:
            return signal.action == side
        return momentum > 0 if side == 'BUY' else momentum < 0

    def _momentum_inverted(self, side: str, signal: Signal) -> bool:
        momentum = self._float((signal.metadata or {}).get('snapshot_momentum_percent'))
        if momentum is None:
            return False
        return momentum < 0 if side == 'BUY' else momentum > 0

    def _structure_invalidated(
        self,
        *,
        side: str,
        candle: Candle,
        breakout_level: float,
        tolerance_price: float,
    ) -> bool:
        return (
            candle.close < breakout_level - tolerance_price
            if side == 'BUY'
            else candle.close > breakout_level + tolerance_price
        )

    def _retest_detected(
        self,
        *,
        side: str,
        candle: Candle,
        breakout_level: float,
        tolerance_price: float,
    ) -> bool:
        if side == 'BUY':
            return candle.low <= breakout_level + tolerance_price and candle.close >= breakout_level - tolerance_price
        return candle.high >= breakout_level - tolerance_price and candle.close <= breakout_level + tolerance_price

    def _continuation_candle(self, *, side: str, candle: Candle, breakout_level: float) -> bool:
        if side == 'BUY':
            return candle.close > candle.open and candle.close > breakout_level
        return candle.close < candle.open and candle.close < breakout_level

    def _updated_retest_extreme(self, *, side: str, previous: float | None, candle: Candle) -> float:
        current = candle.low if side == 'BUY' else candle.high
        if previous is None:
            return current
        return min(previous, current) if side == 'BUY' else max(previous, current)

    def _updated_structure_extreme(self, *, side: str, previous: float | None, candle: Candle) -> float:
        return self._updated_retest_extreme(side=side, previous=previous, candle=candle)

    def _float(self, value) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None
