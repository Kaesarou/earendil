from collections import defaultdict
from datetime import datetime

from app.config.settings import Settings
from app.market.models import MarketSnapshot
from app.risk.models import TradePlan
from app.risk.position_sizing import PositionSizingStrategy
from app.strategies.signals import Signal


class RiskManager:
    def __init__(
        self,
        settings: Settings,
        position_sizing_strategy: PositionSizingStrategy,
    ):
        self.settings = settings
        self.position_sizing_strategy = position_sizing_strategy
        self.trades_today = 0
        self.open_positions = 0
        self.open_positions_by_symbol: dict[str, int] = defaultdict(int)

    def evaluate(
        self,
        signal: Signal,
        snapshot: MarketSnapshot,
        account_equity: float,
    ) -> TradePlan:
        rejection_reason = self._rejection_reason(signal, snapshot.symbol)
        if rejection_reason is not None:
            return TradePlan(approved=False, reason=rejection_reason)

        amount = self.position_sizing_strategy.calculate_amount(
            account_equity=account_equity,
            settings=self.settings,
        )

        if amount <= 0:
            return TradePlan(approved=False, reason='invalid_position_amount')

        if signal.action == 'BUY':
            return self._build_buy_plan(
                signal=signal,
                snapshot=snapshot,
                amount=amount,
            )

        return TradePlan(approved=False, reason=f'unsupported_signal_{signal.action}')

    def record_open_position(self, symbol: str) -> None:
        normalized_symbol = self._normalize_symbol(symbol)
        self.open_positions += 1
        self.open_positions_by_symbol[normalized_symbol] += 1
        self.trades_today += 1

    def record_close_position(self, symbol: str) -> None:
        normalized_symbol = self._normalize_symbol(symbol)

        self.open_positions = max(0, self.open_positions - 1)

        current_symbol_positions = self.open_positions_by_symbol.get(
            normalized_symbol,
            0,
        )
        next_symbol_positions = max(0, current_symbol_positions - 1)

        if next_symbol_positions == 0:
            self.open_positions_by_symbol.pop(normalized_symbol, None)
            return

        self.open_positions_by_symbol[normalized_symbol] = next_symbol_positions

    def _rejection_reason(self, signal: Signal, symbol: str) -> str | None:
        if signal.action == 'HOLD':
            return signal.reason

        if self.open_positions >= self.settings.max_open_positions:
            return 'max_open_positions_reached'

        normalized_symbol = self._normalize_symbol(symbol)
        if (
            self.open_positions_by_symbol.get(normalized_symbol, 0)
            >= self.settings.max_open_positions_per_symbol
            
            ):
            return 'max_open_positions_per_symbol_reached'

        if self.trades_today >= self.settings.max_trades_per_day:
            return 'max_trades_per_day_reached'

        now = datetime.now()
        if (now.hour, now.minute) >= (
            self.settings.force_close_hour,
            self.settings.force_close_minute,
        ):
            return 'too_close_to_daily_shutdown'

        return None

    def _build_buy_plan(
        self,
        signal: Signal,
        snapshot: MarketSnapshot,
        amount: float,
    ) -> TradePlan:
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

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.strip().upper()