from dataclasses import dataclass, replace
from datetime import datetime, timezone

from app.market.models import MarketSnapshot
from app.risk.models import TradePlan
from app.risk.stale_position_guard import (
    STALE_POSITION_EXIT_REASON,
    StalePositionConfig,
    StalePositionGuard,
)


@dataclass(frozen=True)
class TrackedPosition:
    position_id: str
    symbol: str
    side: str
    amount: float
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: datetime
    initial_stop_loss: float | None = None
    highest_price: float | None = None
    lowest_price: float | None = None
    breakeven_stop_enabled: bool = False
    breakeven_trigger_percent: float = 0.0
    breakeven_buffer_percent: float = 0.0
    trailing_stop_enabled: bool = False
    trailing_stop_trigger_percent: float = 0.0
    trailing_stop_distance_percent: float = 0.0
    estimated_total_cost_percent: float = 0.0
    stale_position_enabled: bool = False
    stale_position_max_age_minutes: int = 0
    stale_position_min_favorable_move_percent: float = 0.0
    stale_position_buffer_percent: float = 0.0


@dataclass(frozen=True)
class PositionCloseSignal:
    position_id: str
    symbol: str
    side: str
    exit_price: float
    reason: str
    detected_at: datetime
    metadata: dict[str, float | int | str | bool] | None = None


@dataclass(frozen=True)
class ClosedPosition:
    position_id: str
    symbol: str
    side: str
    amount: float
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    opened_at: datetime
    closed_at: datetime
    duration_seconds: float
    close_reason: str
    gross_pnl: float
    gross_pnl_percent: float


class PositionTracker:
    def __init__(self, stale_position_guard: StalePositionGuard | None = None):
        self.positions: dict[str, TrackedPosition] = {}
        self.stale_position_guard = stale_position_guard or StalePositionGuard()

    def restore_open_position(self, position: TrackedPosition) -> None:
        self.positions[position.position_id] = self._normalize_restored_position(position)

    def open_positions_snapshot(self) -> list[TrackedPosition]:
        return list(self.positions.values())

    def remove_position(self, position_id: str) -> TrackedPosition | None:
        return self.positions.pop(position_id, None)

    def record_open_position(
        self,
        position_id: str,
        trade_plan: TradePlan,
        entry_price: float,
        opened_at: datetime | None = None,
    ) -> TrackedPosition:
        if not trade_plan.symbol:
            raise ValueError(f'Cannot track position without symbol: {trade_plan}')
        if not trade_plan.side:
            raise ValueError(f'Cannot track position without side: {trade_plan}')
        if trade_plan.amount is None:
            raise ValueError(f'Cannot track position without amount: {trade_plan}')
        if trade_plan.stop_loss is None:
            raise ValueError(f'Cannot track position without stop_loss: {trade_plan}')
        if trade_plan.take_profit is None:
            raise ValueError(f'Cannot track position without take_profit: {trade_plan}')

        position = TrackedPosition(
            position_id=position_id,
            symbol=trade_plan.symbol,
            side=trade_plan.side,
            amount=trade_plan.amount,
            entry_price=entry_price,
            stop_loss=trade_plan.stop_loss,
            take_profit=trade_plan.take_profit,
            opened_at=opened_at or datetime.now(timezone.utc),
            initial_stop_loss=trade_plan.stop_loss,
            highest_price=entry_price,
            lowest_price=entry_price,
            breakeven_stop_enabled=trade_plan.breakeven_stop_enabled,
            breakeven_trigger_percent=trade_plan.breakeven_trigger_percent,
            breakeven_buffer_percent=trade_plan.breakeven_buffer_percent,
            trailing_stop_enabled=trade_plan.trailing_stop_enabled,
            trailing_stop_trigger_percent=trade_plan.trailing_stop_trigger_percent,
            trailing_stop_distance_percent=trade_plan.trailing_stop_distance_percent,
            estimated_total_cost_percent=trade_plan.estimated_total_cost_percent or 0.0,
            stale_position_enabled=trade_plan.stale_position_enabled,
            stale_position_max_age_minutes=trade_plan.stale_position_max_age_minutes,
            stale_position_min_favorable_move_percent=(
                trade_plan.stale_position_min_favorable_move_percent
            ),
            stale_position_buffer_percent=trade_plan.stale_position_buffer_percent,
        )

        self.positions[position_id] = position
        return position

    def evaluate_snapshot(self, snapshot: MarketSnapshot) -> list[PositionCloseSignal]:
        close_signals: list[PositionCloseSignal] = []

        for position in list(self.positions.values()):
            if position.symbol != snapshot.symbol:
                continue

            position = self._apply_managed_stop(position, snapshot)
            self.positions[position.position_id] = position

            if position.side == 'BUY':
                close_signal = self._evaluate_buy_position(position, snapshot)
            elif position.side == 'SELL':
                close_signal = self._evaluate_sell_position(position, snapshot)
            else:
                raise ValueError(f'Unsupported tracked position side: {position.side}')

            if close_signal is None:
                close_signal = self._evaluate_stale_position(position, snapshot)

            if close_signal is not None:
                close_signals.append(close_signal)

        return close_signals

    def record_closed_position(
        self,
        close_signal: PositionCloseSignal,
        closed_at: datetime | None = None,
    ) -> ClosedPosition | None:
        position = self.positions.pop(close_signal.position_id, None)
        if position is None:
            return None

        actual_closed_at = closed_at or close_signal.detected_at
        duration_seconds = max(
            0.0,
            (actual_closed_at - position.opened_at).total_seconds(),
        )
        gross_pnl_percent = self._calculate_gross_pnl_percent(
            side=position.side,
            entry_price=position.entry_price,
            exit_price=close_signal.exit_price,
        )
        gross_pnl = position.amount * (gross_pnl_percent / 100)

        return ClosedPosition(
            position_id=position.position_id,
            symbol=position.symbol,
            side=position.side,
            amount=position.amount,
            entry_price=position.entry_price,
            exit_price=close_signal.exit_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            opened_at=position.opened_at,
            closed_at=actual_closed_at,
            duration_seconds=round(duration_seconds, 3),
            close_reason=close_signal.reason,
            gross_pnl=round(gross_pnl, 4),
            gross_pnl_percent=round(gross_pnl_percent, 4),
        )

    def has_open_positions(self) -> bool:
        return bool(self.positions)

    def _apply_managed_stop(
        self,
        position: TrackedPosition,
        snapshot: MarketSnapshot,
    ) -> TrackedPosition:
        if position.side == 'BUY':
            return self._apply_buy_managed_stop(position, snapshot)
        if position.side == 'SELL':
            return self._apply_sell_managed_stop(position, snapshot)
        return position

    def _apply_buy_managed_stop(
        self,
        position: TrackedPosition,
        snapshot: MarketSnapshot,
    ) -> TrackedPosition:
        highest_price = max(position.highest_price or position.entry_price, snapshot.last)
        stop_loss = position.stop_loss
        gain_percent = self._calculate_gross_pnl_percent('BUY', position.entry_price, snapshot.last)

        if position.breakeven_stop_enabled and gain_percent >= position.breakeven_trigger_percent:
            stop_loss = max(
                stop_loss,
                position.entry_price * (1 + position.breakeven_buffer_percent / 100),
            )

        if position.trailing_stop_enabled and gain_percent >= position.trailing_stop_trigger_percent:
            stop_loss = max(
                stop_loss,
                highest_price * (1 - position.trailing_stop_distance_percent / 100),
            )

        return replace(position, highest_price=highest_price, stop_loss=round(stop_loss, 5))

    def _apply_sell_managed_stop(
        self,
        position: TrackedPosition,
        snapshot: MarketSnapshot,
    ) -> TrackedPosition:
        lowest_price = min(position.lowest_price or position.entry_price, snapshot.last)
        stop_loss = position.stop_loss
        gain_percent = self._calculate_gross_pnl_percent('SELL', position.entry_price, snapshot.last)

        if position.breakeven_stop_enabled and gain_percent >= position.breakeven_trigger_percent:
            stop_loss = min(
                stop_loss,
                position.entry_price * (1 - position.breakeven_buffer_percent / 100),
            )

        if position.trailing_stop_enabled and gain_percent >= position.trailing_stop_trigger_percent:
            stop_loss = min(
                stop_loss,
                lowest_price * (1 + position.trailing_stop_distance_percent / 100),
            )

        return replace(position, lowest_price=lowest_price, stop_loss=round(stop_loss, 5))

    def _evaluate_buy_position(
        self,
        position: TrackedPosition,
        snapshot: MarketSnapshot,
    ) -> PositionCloseSignal | None:
        if snapshot.last <= position.stop_loss:
            return PositionCloseSignal(
                position_id=position.position_id,
                symbol=position.symbol,
                side=position.side,
                exit_price=snapshot.last,
                reason=self._managed_stop_reason(position),
                detected_at=snapshot.timestamp,
            )
        if snapshot.last >= position.take_profit:
            return PositionCloseSignal(
                position_id=position.position_id,
                symbol=position.symbol,
                side=position.side,
                exit_price=snapshot.last,
                reason='take_profit_hit',
                detected_at=snapshot.timestamp,
            )
        return None

    def _evaluate_sell_position(
        self,
        position: TrackedPosition,
        snapshot: MarketSnapshot,
    ) -> PositionCloseSignal | None:
        if snapshot.last >= position.stop_loss:
            return PositionCloseSignal(
                position_id=position.position_id,
                symbol=position.symbol,
                side=position.side,
                exit_price=snapshot.last,
                reason=self._managed_stop_reason(position),
                detected_at=snapshot.timestamp,
            )
        if snapshot.last <= position.take_profit:
            return PositionCloseSignal(
                position_id=position.position_id,
                symbol=position.symbol,
                side=position.side,
                exit_price=snapshot.last,
                reason='take_profit_hit',
                detected_at=snapshot.timestamp,
            )
        return None

    def _evaluate_stale_position(
        self,
        position: TrackedPosition,
        snapshot: MarketSnapshot,
    ) -> PositionCloseSignal | None:
        decision = self.stale_position_guard.evaluate(
            side=position.side,
            entry_price=position.entry_price,
            highest_price=position.highest_price,
            lowest_price=position.lowest_price,
            opened_at=position.opened_at,
            now=snapshot.timestamp,
            estimated_total_cost_percent=position.estimated_total_cost_percent,
            config=StalePositionConfig(
                enabled=position.stale_position_enabled,
                max_age_minutes=position.stale_position_max_age_minutes,
                min_favorable_move_percent=(
                    position.stale_position_min_favorable_move_percent
                ),
                buffer_percent=position.stale_position_buffer_percent,
            ),
        )

        if not decision.should_close:
            return None

        return PositionCloseSignal(
            position_id=position.position_id,
            symbol=position.symbol,
            side=position.side,
            exit_price=snapshot.last,
            reason=decision.reason or STALE_POSITION_EXIT_REASON,
            detected_at=snapshot.timestamp,
            metadata={
                'stale_position_action': 'CLOSE',
                'stale_position_age_minutes': round(decision.age_minutes, 4),
                'stale_position_mfe_percent': round(decision.mfe_percent, 4),
                'stale_position_required_mfe_percent': round(
                    decision.required_mfe_percent,
                    4,
                ),
                'estimated_total_cost_percent': round(
                    decision.estimated_total_cost_percent,
                    4,
                ),
                'stale_position_max_age_minutes': position.stale_position_max_age_minutes,
                'stale_position_min_favorable_move_percent': (
                    position.stale_position_min_favorable_move_percent
                ),
                'stale_position_buffer_percent': position.stale_position_buffer_percent,
            },
        )

    def _managed_stop_reason(self, position: TrackedPosition) -> str:
        if position.side == 'BUY':
            break_even_price = position.entry_price * (1 + position.breakeven_buffer_percent / 100)
            if position.trailing_stop_enabled and position.stop_loss > break_even_price:
                return 'trailing_stop_hit'
            if position.breakeven_stop_enabled and position.stop_loss >= break_even_price:
                return 'break_even_stop_hit'
        if position.side == 'SELL':
            break_even_price = position.entry_price * (1 - position.breakeven_buffer_percent / 100)
            if position.trailing_stop_enabled and position.stop_loss < break_even_price:
                return 'trailing_stop_hit'
            if position.breakeven_stop_enabled and position.stop_loss <= break_even_price:
                return 'break_even_stop_hit'
        return 'stop_loss_hit'

    def _normalize_restored_position(self, position: TrackedPosition) -> TrackedPosition:
        return replace(
            position,
            initial_stop_loss=position.initial_stop_loss or position.stop_loss,
            highest_price=position.highest_price or position.entry_price,
            lowest_price=position.lowest_price or position.entry_price,
        )

    def _calculate_gross_pnl_percent(
        self,
        side: str,
        entry_price: float,
        exit_price: float,
    ) -> float:
        if entry_price <= 0:
            raise ValueError(f'Cannot calculate PnL with invalid entry_price={entry_price}')
        if side == 'BUY':
            return ((exit_price - entry_price) / entry_price) * 100
        if side == 'SELL':
            return ((entry_price - exit_price) / entry_price) * 100
        raise ValueError(f'Unsupported position side for PnL calculation: {side}')
