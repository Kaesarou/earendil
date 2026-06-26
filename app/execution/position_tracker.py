from dataclasses import dataclass
from datetime import datetime, timezone

from app.market.models import MarketSnapshot
from app.risk.models import TradePlan


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


@dataclass(frozen=True)
class PositionCloseSignal:
    position_id: str
    symbol: str
    side: str
    exit_price: float
    reason: str
    detected_at: datetime


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
    def __init__(self):
        self.positions: dict[str, TrackedPosition] = {}

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
        )

        self.positions[position_id] = position
        return position

    def evaluate_snapshot(self, snapshot: MarketSnapshot) -> list[PositionCloseSignal]:
        close_signals: list[PositionCloseSignal] = []

        for position in self.positions.values():
            if position.symbol != snapshot.symbol:
                continue

            if position.side == 'BUY':
                close_signal = self._evaluate_buy_position(position, snapshot)
            elif position.side == 'SELL':
                close_signal = self._evaluate_sell_position(position, snapshot)
            else:
                raise ValueError(f'Unsupported tracked position side: {position.side}')

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
                reason='stop_loss_hit',
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
                reason='stop_loss_hit',
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