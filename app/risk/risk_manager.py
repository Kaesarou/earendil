from dataclasses import dataclass
from datetime import datetime

from app.config.settings import Settings
from app.market.models import MarketSnapshot
from app.strategies.signals import Signal


@dataclass(frozen=True)
class TradePlan:
    approved: bool
    reason: str
    symbol: str | None = None
    side: str | None = None
    amount: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None


class RiskManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.trades_today = 0
        self.open_positions = 0

    def evaluate(self, signal: Signal, snapshot: MarketSnapshot, account_equity: float) -> TradePlan:
        if signal.action == 'HOLD':
            return TradePlan(approved=False, reason=signal.reason)

        if self.open_positions >= self.settings.max_open_positions:
            return TradePlan(approved=False, reason='max_open_positions_reached')

        if self.trades_today >= self.settings.max_trades_per_day:
            return TradePlan(approved=False, reason='max_trades_per_day_reached')

        now = datetime.now()
        if (now.hour, now.minute) >= (self.settings.force_close_hour, self.settings.force_close_minute):
            return TradePlan(approved=False, reason='too_close_to_daily_shutdown')

        max_position_amount = account_equity * (self.settings.max_position_size_percent / 100)
        amount = max(0.0, round(max_position_amount, 2))

        if amount <= 0:
            return TradePlan(approved=False, reason='invalid_position_amount')

        if signal.action == 'BUY':
            stop_loss = snapshot.last * (1 - self.settings.stop_loss_percent / 100)
            take_profit = snapshot.last * (1 + self.settings.take_profit_percent / 100)
            return TradePlan(
                approved=True,
                reason=signal.reason,
                symbol=snapshot.symbol,
                side='BUY',
                amount=amount,
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
            )

        return TradePlan(approved=False, reason=f'unsupported_signal_{signal.action}')

    def record_open_position(self) -> None:
        self.open_positions += 1
        self.trades_today += 1

    def record_close_position(self) -> None:
        self.open_positions = max(0, self.open_positions - 1)
