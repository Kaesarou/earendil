from dataclasses import dataclass

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


@dataclass(frozen=True)
class PositionCloseSignal:
    position_id: str
    symbol: str
    side: str
    exit_price: float
    reason: str


class PositionTracker:
    def __init__(self):
        self.positions: dict[str, TrackedPosition] = {}

    def record_open_position(
        self,
        position_id: str,
        trade_plan: TradePlan,
        entry_price: float,
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
                if close_signal is not None:
                    close_signals.append(close_signal)

        return close_signals

    def record_closed_position(self, position_id: str) -> TrackedPosition | None:
        return self.positions.pop(position_id, None)

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
            )

        if snapshot.last >= position.take_profit:
            return PositionCloseSignal(
                position_id=position.position_id,
                symbol=position.symbol,
                side=position.side,
                exit_price=snapshot.last,
                reason='take_profit_hit',
            )

        return None