from dataclasses import dataclass

from app.market.models import Candle
from app.strategies.signals import Signal


@dataclass(frozen=True)
class MoveExhaustionConfig:
    extension_soft_percent: float = 1.5
    extension_hard_percent: float = 3.5
    near_extreme_distance_percent: float = 0.20
    deceleration_threshold_percent: float = 0.08
    weak_close_quality_percent: float = 78.0
    max_penalty_points: float = 18.0
    medium_risk_threshold: float = 25.0
    high_risk_threshold: float = 50.0
    severe_risk_threshold: float = 75.0


@dataclass(frozen=True)
class MoveExhaustionAnalysis:
    late_entry_risk: float
    exhaustion_penalty: float
    move_extension_percent: float
    extension_atr_ratio: float
    distance_to_recent_high_percent: float
    distance_to_recent_low_percent: float
    momentum_acceleration_percent: float
    momentum_deceleration_detected: bool
    remaining_move_quality: str
    reason_exhaustion_components: tuple[str, ...]
    late_entry_severity: str = 'LOW'


class MoveExhaustionAnalyzer:
    def __init__(self, config: MoveExhaustionConfig | None = None):
        self.config = config or MoveExhaustionConfig()

    def analyze(
        self,
        *,
        candle: Candle,
        signal: Signal,
        close_quality: float,
    ) -> MoveExhaustionAnalysis:
        metadata = signal.metadata or {}
        side = signal.action
        session_move_percent = self._float_metadata(metadata, 'session_move_percent')
        atr_percent = self._float_metadata(metadata, 'atr_percent')
        snapshot_momentum_percent = self._float_metadata(
            metadata,
            'snapshot_momentum_percent',
        )
        has_momentum_metadata = 'snapshot_momentum_percent' in metadata

        directional_session_move = self._directional_value(
            value=session_move_percent,
            side=side,
        )
        directional_snapshot_momentum = self._directional_value(
            value=snapshot_momentum_percent,
            side=side,
        )
        move_extension_percent = max(directional_session_move, 0.0)
        extension_factor = self._bounded_ratio(
            value=move_extension_percent,
            soft=self.config.extension_soft_percent,
            hard=self.config.extension_hard_percent,
        )
        extension_atr_ratio = (
            move_extension_percent / atr_percent
            if atr_percent > 0
            else 0.0
        )

        distance_to_recent_high_percent = self._distance_to_high_percent(candle)
        distance_to_recent_low_percent = self._distance_to_low_percent(candle)
        distance_to_trade_extreme_percent = (
            distance_to_recent_high_percent
            if side == 'BUY'
            else distance_to_recent_low_percent
        )
        proximity_factor = self._proximity_factor(distance_to_trade_extreme_percent)

        momentum_acceleration_percent = directional_snapshot_momentum - (
            move_extension_percent / 10
        )
        momentum_deceleration_detected = (
            has_momentum_metadata
            and move_extension_percent >= self.config.extension_soft_percent
            and directional_snapshot_momentum < self.config.deceleration_threshold_percent
        )
        deceleration_factor = 1.0 if momentum_deceleration_detected else 0.0

        weak_close_factor = self._bounded_ratio(
            value=max(self.config.weak_close_quality_percent - close_quality, 0.0),
            soft=0.0,
            hard=self.config.weak_close_quality_percent,
        )

        late_entry_risk = 0.0
        late_entry_risk += 15.0 * extension_factor
        late_entry_risk += 25.0 * extension_factor * proximity_factor
        late_entry_risk += 30.0 * extension_factor * deceleration_factor
        late_entry_risk += 20.0 * extension_factor * weak_close_factor
        late_entry_risk = min(late_entry_risk, 100.0)

        return MoveExhaustionAnalysis(
            late_entry_risk=round(late_entry_risk, 4),
            exhaustion_penalty=round(
                self.config.max_penalty_points * late_entry_risk / 100,
                4,
            ),
            move_extension_percent=round(move_extension_percent, 4),
            extension_atr_ratio=round(extension_atr_ratio, 4),
            distance_to_recent_high_percent=round(
                distance_to_recent_high_percent,
                4,
            ),
            distance_to_recent_low_percent=round(
                distance_to_recent_low_percent,
                4,
            ),
            momentum_acceleration_percent=round(
                momentum_acceleration_percent,
                4,
            ),
            momentum_deceleration_detected=momentum_deceleration_detected,
            remaining_move_quality=self._remaining_move_quality(late_entry_risk),
            reason_exhaustion_components=self._reason_components(
                extension_factor=extension_factor,
                proximity_factor=proximity_factor,
                momentum_deceleration_detected=momentum_deceleration_detected,
                weak_close_factor=weak_close_factor,
            ),
            late_entry_severity=self._late_entry_severity(late_entry_risk),
        )

    def _directional_value(self, *, value: float, side: str) -> float:
        if side == 'SELL':
            return -value
        return value

    def _distance_to_high_percent(self, candle: Candle) -> float:
        if candle.close <= 0:
            return 0.0
        return max(((candle.high - candle.close) / candle.close) * 100, 0.0)

    def _distance_to_low_percent(self, candle: Candle) -> float:
        if candle.close <= 0:
            return 0.0
        return max(((candle.close - candle.low) / candle.close) * 100, 0.0)

    def _bounded_ratio(self, *, value: float, soft: float, hard: float) -> float:
        if hard <= soft:
            return 1.0 if value > soft else 0.0
        if value <= soft:
            return 0.0
        if value >= hard:
            return 1.0
        return (value - soft) / (hard - soft)

    def _proximity_factor(self, distance_percent: float) -> float:
        if self.config.near_extreme_distance_percent <= 0:
            return 1.0
        return max(
            1 - (distance_percent / self.config.near_extreme_distance_percent),
            0.0,
        )

    def _reason_components(
        self,
        *,
        extension_factor: float,
        proximity_factor: float,
        momentum_deceleration_detected: bool,
        weak_close_factor: float,
    ) -> tuple[str, ...]:
        components: list[str] = []
        if extension_factor > 0:
            components.append('extended_move')
        if proximity_factor > 0:
            components.append('near_trade_extreme')
        if momentum_deceleration_detected:
            components.append('momentum_deceleration')
        if weak_close_factor > 0:
            components.append('weak_close_quality_after_extension')
        return tuple(components)

    def _remaining_move_quality(self, late_entry_risk: float) -> str:
        if late_entry_risk >= 70:
            return 'POOR'
        if late_entry_risk >= 40:
            return 'ACCEPTABLE'
        return 'GOOD'

    def _late_entry_severity(self, late_entry_risk: float) -> str:
        if late_entry_risk >= self.config.severe_risk_threshold:
            return 'SEVERE'
        if late_entry_risk >= self.config.high_risk_threshold:
            return 'HIGH'
        if late_entry_risk >= self.config.medium_risk_threshold:
            return 'MEDIUM'
        return 'LOW'

    def _float_metadata(self, metadata: dict, key: str) -> float:
        value = metadata.get(key, 0.0)
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
