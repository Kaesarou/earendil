from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import InstrumentProfile, RiskProfile
from app.market.models import MarketSnapshot
from app.risk.models import TradePlan
from app.risk.position_sizing import PositionSizingStrategy
from app.strategies.signals import Signal
from app.utils.commons import normalize_symbol


@dataclass(frozen=True)
class EffectiveRisk:
    stop_loss_percent: float
    take_profit_percent: float
    atr_percent: float | None
    dynamic_sl_tp_enabled: bool


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
        effective_risk = self._effective_risk(signal, risk_profile)
        spread_percent = self._calculate_spread_percent(snapshot)
        expected_move_percent = effective_risk.take_profit_percent
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
            return self._rejected_plan(
                reason=rejection_reason,
                signal=signal,
                snapshot=snapshot,
                risk_profile=risk_profile,
                effective_risk=effective_risk,
                spread_percent=spread_percent,
                expected_move_percent=expected_move_percent,
                min_required_move_percent=min_required_move_percent,
            )

        amount = self.position_sizing_strategy.calculate_amount(
            account_equity=account_equity,
            risk_profile=risk_profile,
        )

        if amount <= 0:
            return self._rejected_plan(
                reason='invalid_position_amount',
                signal=signal,
                snapshot=snapshot,
                risk_profile=risk_profile,
                effective_risk=effective_risk,
                spread_percent=spread_percent,
                expected_move_percent=expected_move_percent,
                min_required_move_percent=min_required_move_percent,
            )

        expected_gross_profit = self._calculate_expected_gross_profit(
            amount=amount,
            effective_risk=effective_risk,
        )
        estimated_fees = risk_profile.estimated_round_trip_fees
        expected_net_profit = expected_gross_profit - estimated_fees

        if expected_net_profit < risk_profile.min_expected_net_profit:
            return self._rejected_plan(
                reason='expected_profit_too_low_after_fees',
                signal=signal,
                snapshot=snapshot,
                risk_profile=risk_profile,
                effective_risk=effective_risk,
                spread_percent=spread_percent,
                expected_move_percent=expected_move_percent,
                min_required_move_percent=min_required_move_percent,
                amount=amount,
                expected_gross_profit=expected_gross_profit,
                estimated_fees=estimated_fees,
                expected_net_profit=expected_net_profit,
            )

        return self._build_trade_plan(
            signal=signal,
            snapshot=snapshot,
            amount=amount,
            expected_gross_profit=expected_gross_profit,
            estimated_fees=estimated_fees,
            expected_net_profit=expected_net_profit,
            risk_profile=risk_profile,
            effective_risk=effective_risk,
            spread_percent=spread_percent,
            expected_move_percent=expected_move_percent,
            min_required_move_percent=min_required_move_percent,
        )

    def instrument_profile_for(self, symbol: str) -> InstrumentProfile:
        return self.instrument_registry.resolve(symbol)

    def risk_profile_for(self, symbol: str) -> RiskProfile:
        return self.instrument_registry.risk_profile_for(symbol)

    def record_open_position(self, symbol: str) -> None:
        normalized_symbol = normalize_symbol(symbol)
        self.open_positions += 1
        self.open_positions_by_symbol[normalized_symbol] += 1
        self.trades_today += 1

    def restore_open_position(self, symbol: str) -> None:
        normalized_symbol = normalize_symbol(symbol)
        self.open_positions += 1
        self.open_positions_by_symbol[normalized_symbol] += 1

    def record_close_position(self, symbol: str) -> None:
        normalized_symbol = normalize_symbol(symbol)

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

        if self.open_positions >= self.settings.max_open_positions:
            return 'max_open_positions_reached'

        normalized_symbol = normalize_symbol(symbol)
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

    def _rejected_plan(
        self,
        reason: str,
        signal: Signal,
        snapshot: MarketSnapshot,
        risk_profile: RiskProfile,
        effective_risk: EffectiveRisk,
        spread_percent: float | None,
        expected_move_percent: float,
        min_required_move_percent: float | None,
        amount: float | None = None,
        expected_gross_profit: float | None = None,
        estimated_fees: float | None = None,
        expected_net_profit: float | None = None,
    ) -> TradePlan:
        return TradePlan(
            approved=False,
            reason=reason,
            symbol=snapshot.symbol,
            side=signal.action,
            amount=self._round_optional(amount),
            expected_gross_profit=self._round_optional(expected_gross_profit),
            estimated_fees=self._round_optional(estimated_fees),
            expected_net_profit=self._round_optional(expected_net_profit),
            spread_percent=self._round_optional(spread_percent),
            max_spread_percent=risk_profile.max_spread_percent,
            expected_move_percent=round(expected_move_percent, 4),
            min_required_move_percent=self._round_optional(min_required_move_percent),
            min_move_spread_ratio=risk_profile.min_move_spread_ratio,
            atr_percent=self._round_optional(effective_risk.atr_percent),
            dynamic_sl_tp_enabled=effective_risk.dynamic_sl_tp_enabled,
            effective_stop_loss_percent=round(effective_risk.stop_loss_percent, 4),
            effective_take_profit_percent=round(effective_risk.take_profit_percent, 4),
        )

    def _build_trade_plan(
        self,
        signal: Signal,
        snapshot: MarketSnapshot,
        amount: float,
        expected_gross_profit: float,
        estimated_fees: float,
        expected_net_profit: float,
        risk_profile: RiskProfile,
        effective_risk: EffectiveRisk,
        spread_percent: float | None,
        expected_move_percent: float,
        min_required_move_percent: float | None,
    ) -> TradePlan:
        if signal.action == 'BUY':
            stop_loss = snapshot.last * (1 - effective_risk.stop_loss_percent / 100)
            take_profit = snapshot.last * (1 + effective_risk.take_profit_percent / 100)
        elif signal.action == 'SELL':
            stop_loss = snapshot.last * (1 + effective_risk.stop_loss_percent / 100)
            take_profit = snapshot.last * (1 - effective_risk.take_profit_percent / 100)
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
            atr_percent=self._round_optional(effective_risk.atr_percent),
            dynamic_sl_tp_enabled=effective_risk.dynamic_sl_tp_enabled,
            effective_stop_loss_percent=round(effective_risk.stop_loss_percent, 4),
            effective_take_profit_percent=round(effective_risk.take_profit_percent, 4),
            breakeven_stop_enabled=risk_profile.breakeven_stop_enabled,
            breakeven_trigger_percent=risk_profile.breakeven_trigger_percent,
            breakeven_buffer_percent=risk_profile.breakeven_buffer_percent,
            trailing_stop_enabled=risk_profile.trailing_stop_enabled,
            trailing_stop_trigger_percent=risk_profile.trailing_stop_trigger_percent,
            trailing_stop_distance_percent=risk_profile.trailing_stop_distance_percent,
        )

    def _calculate_expected_gross_profit(
        self,
        amount: float,
        effective_risk: EffectiveRisk,
    ) -> float:
        return amount * (effective_risk.take_profit_percent / 100)

    def _effective_risk(
        self,
        signal: Signal,
        risk_profile: RiskProfile,
    ) -> EffectiveRisk:
        atr_percent = self._atr_percent_from_signal(signal)

        if not risk_profile.dynamic_sl_tp_enabled or atr_percent is None:
            return EffectiveRisk(
                stop_loss_percent=risk_profile.stop_loss_percent,
                take_profit_percent=risk_profile.take_profit_percent,
                atr_percent=atr_percent,
                dynamic_sl_tp_enabled=False,
            )

        stop_loss_percent = atr_percent * risk_profile.stop_loss_atr_multiplier
        take_profit_percent = atr_percent * risk_profile.take_profit_atr_multiplier

        stop_loss_percent = self._clamp_percent(
            value=stop_loss_percent,
            minimum=risk_profile.min_stop_loss_percent,
            maximum=risk_profile.max_stop_loss_percent,
        )
        take_profit_percent = self._clamp_percent(
            value=take_profit_percent,
            minimum=risk_profile.min_take_profit_percent,
            maximum=risk_profile.max_take_profit_percent,
        )

        return EffectiveRisk(
            stop_loss_percent=stop_loss_percent,
            take_profit_percent=take_profit_percent,
            atr_percent=atr_percent,
            dynamic_sl_tp_enabled=True,
        )

    def _atr_percent_from_signal(self, signal: Signal) -> float | None:
        if signal.metadata is None:
            return None

        raw_atr_percent = signal.metadata.get('atr_percent')
        if raw_atr_percent is None:
            return None

        try:
            atr_percent = float(raw_atr_percent)
        except (TypeError, ValueError):
            return None

        if atr_percent <= 0:
            return None

        return atr_percent

    def _clamp_percent(self, value: float, minimum: float, maximum: float) -> float:
        if minimum > 0:
            value = max(value, minimum)

        if maximum > 0:
            value = min(value, maximum)

        return value

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
