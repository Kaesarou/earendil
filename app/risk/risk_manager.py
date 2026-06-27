from collections import defaultdict
from datetime import datetime

from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import InstrumentProfile, RiskProfile
from app.market.models import MarketSnapshot
from app.risk.models import TradePlan
from app.risk.position_sizing import PositionSizingStrategy
from app.strategies.signals import Signal


class RiskManager:
    def __init__(
        self,
        settings: Settings,
        position_sizing_strategy: PositionSizingStrategy,
        instrument_registry: InstrumentRegistry,
    ):
        self.settings = settings
        self.position_sizing_strategy = position_sizing_strategy
        self.instrument_registry = instrument_registry
        self.trades_today = 0
        self.open_positions = 0
        self.open_positions_by_symbol: dict[str, int] = defaultdict(int)

    def evaluate(
        self,
        signal: Signal,
        snapshot: MarketSnapshot,
        account_equity: float,
    ) -> TradePlan:
        risk_profile = self.risk_profile_for(snapshot.symbol)
        spread_percent = self._calculate_spread_percent(snapshot)
        expected_move_percent = risk_profile.take_profit_percent
        min_required_move_percent = self._calculate_min_required_move_percent(
            spread_percent=spread_percent,
            risk_profile=risk_profile,
        )

        rejection_reason = self._rejection_reason(
            signal=signal,
            symbol=snapshot.symbol,
            risk_profile=risk_profile,
            spread_percent=spread_percent,
            expected_move_percent=expected_move_percent,
            min_required_move_percent=min_required_move_percent,
        )
        if rejection_reason is not None:
            return TradePlan(
                approved=False,
                reason=rejection_reason,
                symbol=snapshot.symbol,
                side=signal.action,
                spread_percent=self._round_optional(spread_percent),
                max_spread_percent=risk_profile.max_spread_percent,
                expected_move_percent=round(expected_move_percent, 4),
                min_required_move_percent=self._round_optional(min_required_move_percent),
                min_move_spread_ratio=risk_profile.min_move_spread_ratio,
            )

        amount = self.position_sizing_strategy.calculate_amount(
            account_equity=account_equity,
            risk_profile=risk_profile,
        )

        if amount <= 0:
            return TradePlan(
                approved=False,
                reason='invalid_position_amount',
                symbol=snapshot.symbol,
                side=signal.action,
                spread_percent=self._round_optional(spread_percent),
                max_spread_percent=risk_profile.max_spread_percent,
                expected_move_percent=round(expected_move_percent, 4),
                min_required_move_percent=self._round_optional(min_required_move_percent),
                min_move_spread_ratio=risk_profile.min_move_spread_ratio,
            )

        expected_gross_profit = self._calculate_expected_gross_profit(
            amount=amount,
            risk_profile=risk_profile,
        )
        estimated_fees = risk_profile.estimated_round_trip_fees
        expected_net_profit = expected_gross_profit - estimated_fees

        if expected_net_profit < risk_profile.min_expected_net_profit:
            return TradePlan(
                approved=False,
                reason='expected_profit_too_low_after_fees',
                symbol=snapshot.symbol,
                side=signal.action,
                amount=round(amount, 4),
                expected_gross_profit=round(expected_gross_profit, 4),
                estimated_fees=round(estimated_fees, 4),
                expected_net_profit=round(expected_net_profit, 4),
                spread_percent=self._round_optional(spread_percent),
                max_spread_percent=risk_profile.max_spread_percent,
                expected_move_percent=round(expected_move_percent, 4),
                min_required_move_percent=self._round_optional(min_required_move_percent),
                min_move_spread_ratio=risk_profile.min_move_spread_ratio,
            )

        return self._build_trade_plan(
            signal=signal,
            snapshot=snapshot,
            amount=amount,
            expected_gross_profit=expected_gross_profit,
            estimated_fees=estimated_fees,
            expected_net_profit=expected_net_profit,
            risk_profile=risk_profile,
            spread_percent=spread_percent,
            expected_move_percent=expected_move_percent,
            min_required_move_percent=min_required_move_percent,
        )

    def instrument_profile_for(self, symbol: str) -> InstrumentProfile:
        return self.instrument_registry.resolve(symbol)

    def risk_profile_for(self, symbol: str) -> RiskProfile:
        return self.instrument_registry.risk_profile_for(symbol)

    def record_open_position(self, symbol: str) -> None:
        normalized_symbol = self._normalize_symbol(symbol)
        self.open_positions += 1
        self.open_positions_by_symbol[normalized_symbol] += 1
        self.trades_today += 1

    def restore_open_position(self, symbol: str) -> None:
        normalized_symbol = self._normalize_symbol(symbol)
        self.open_positions += 1
        self.open_positions_by_symbol[normalized_symbol] += 1

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

    def _rejection_reason(
        self,
        signal: Signal,
        symbol: str,
        risk_profile: RiskProfile,
        spread_percent: float | None,
        expected_move_percent: float,
        min_required_move_percent: float | None,
    ) -> str | None:
        if signal.action == 'HOLD':
            return signal.reason

        if signal.action not in ('BUY', 'SELL'):
            return f'unsupported_signal_{signal.action}'

        if signal.action == 'SELL' and not self.settings.short_selling_enabled:
            return 'short_selling_disabled'

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

        if risk_profile.force_close_enabled:
            now = datetime.now()
            if (now.hour, now.minute) >= (
                risk_profile.force_close_hour,
                risk_profile.force_close_minute,
            ):
                return 'too_close_to_daily_shutdown'

        if (
            spread_percent is not None
            and risk_profile.max_spread_percent > 0
            and spread_percent > risk_profile.max_spread_percent
        ):
            return 'spread_too_high'

        if (
            min_required_move_percent is not None
            and risk_profile.min_move_spread_ratio > 0
            and expected_move_percent < min_required_move_percent
        ):
            return 'expected_move_too_low_vs_spread'

        return None

    def _build_trade_plan(
        self,
        signal: Signal,
        snapshot: MarketSnapshot,
        amount: float,
        expected_gross_profit: float,
        estimated_fees: float,
        expected_net_profit: float,
        risk_profile: RiskProfile,
        spread_percent: float | None,
        expected_move_percent: float,
        min_required_move_percent: float | None,
    ) -> TradePlan:
        if signal.action == 'BUY':
            stop_loss = snapshot.last * (1 - risk_profile.stop_loss_percent / 100)
            take_profit = snapshot.last * (1 + risk_profile.take_profit_percent / 100)
        elif signal.action == 'SELL':
            stop_loss = snapshot.last * (1 + risk_profile.stop_loss_percent / 100)
            take_profit = snapshot.last * (1 - risk_profile.take_profit_percent / 100)
        else:
            raise ValueError(f'Unsupported signal action for trade plan: {signal.action}')

        return TradePlan(
            approved=True,
            reason=signal.reason,
            symbol=snapshot.symbol,
            side=signal.action,
            amount=round(amount, 4),
            stop_loss=round(stop_loss, 5),
            take_profit=round(take_profit, 5),
            expected_gross_profit=round(expected_gross_profit, 4),
            estimated_fees=round(estimated_fees, 4),
            expected_net_profit=round(expected_net_profit, 4),
            spread_percent=self._round_optional(spread_percent),
            max_spread_percent=risk_profile.max_spread_percent,
            expected_move_percent=round(expected_move_percent, 4),
            min_required_move_percent=self._round_optional(min_required_move_percent),
            min_move_spread_ratio=risk_profile.min_move_spread_ratio,
        )

    def _calculate_expected_gross_profit(
        self,
        amount: float,
        risk_profile: RiskProfile,
    ) -> float:
        return amount * (risk_profile.take_profit_percent / 100)

    def _calculate_spread_percent(self, snapshot: MarketSnapshot) -> float | None:
        if snapshot.bid <= 0 or snapshot.ask <= 0 or snapshot.last <= 0:
            return None

        spread = snapshot.ask - snapshot.bid
        if spread < 0:
            return None

        return (spread / snapshot.last) * 100

    def _calculate_min_required_move_percent(
        self,
        spread_percent: float | None,
        risk_profile: RiskProfile,
    ) -> float | None:
        if spread_percent is None:
            return None

        return spread_percent * risk_profile.min_move_spread_ratio

    def _round_optional(self, value: float | None) -> float | None:
        if value is None:
            return None

        return round(value, 4)

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.strip().upper()
