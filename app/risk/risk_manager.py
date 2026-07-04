from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import InstrumentProfile, RiskProfile
from app.market.models import MarketSnapshot
from app.risk.models import TradePlan
from app.risk.position_sizing import PositionSizingStrategy
from app.risk.trade_cost_model import TradeCostEstimate, TradeCostModel
from app.strategies.signals import Signal
from app.utils.commons import normalize_symbol, spread_percent as calculate_spread_percent


@dataclass(frozen=True)
class EffectiveRisk:
    stop_loss_percent: float
    take_profit_percent: float
    atr_percent: float | None
    dynamic_sl_tp_enabled: bool


@dataclass(frozen=True)
class TradeCostPlanFields:
    expected_gross_profit: float | None = None
    expected_net_profit: float | None = None
    expected_net_profit_percent: float | None = None
    required_min_expected_net_profit_amount: float | None = None
    min_expected_net_profit_percent: float | None = None
    estimated_fees: float | None = None
    estimated_open_fee: float | None = None
    estimated_close_fee: float | None = None
    estimated_fixed_fees: float | None = None
    estimated_spread_cost: float | None = None
    estimated_total_cost: float | None = None
    estimated_total_cost_percent: float | None = None


class RiskManager:
    def __init__(
        self,
        settings: Settings,
        position_sizing_strategy: PositionSizingStrategy,
        instrument_registry: InstrumentRegistry,
        trade_cost_model: TradeCostModel | None = None,
    ):
        self.settings = settings
        self.position_sizing_strategy = position_sizing_strategy
        self.instrument_registry = instrument_registry
        self.trade_cost_model = trade_cost_model or TradeCostModel()
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

        trade_cost_estimate = self.trade_cost_model.estimate(
            position_value=amount,
            expected_move_percent=expected_move_percent,
            spread_percent=spread_percent,
            config=risk_profile.trade_cost,
        )

        if (
            trade_cost_estimate.expected_net_profit_percent
            < trade_cost_estimate.min_expected_net_profit_percent
        ):
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
                trade_cost_estimate=trade_cost_estimate,
            )

        return self._build_trade_plan(
            signal=signal,
            snapshot=snapshot,
            amount=amount,
            trade_cost_estimate=trade_cost_estimate,
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
        trade_cost_estimate: TradeCostEstimate | None = None,
    ) -> TradePlan:
        trade_cost_fields = self._trade_cost_plan_fields(trade_cost_estimate)

        return TradePlan(
            approved=False,
            reason=reason,
            symbol=snapshot.symbol,
            side=signal.action,
            amount=self._round_optional(amount),
            expected_gross_profit=trade_cost_fields.expected_gross_profit,
            expected_net_profit=trade_cost_fields.expected_net_profit,
            expected_net_profit_percent=trade_cost_fields.expected_net_profit_percent,
            required_min_expected_net_profit_amount=(
                trade_cost_fields.required_min_expected_net_profit_amount
            ),
            min_expected_net_profit_percent=trade_cost_fields.min_expected_net_profit_percent,
            estimated_fees=trade_cost_fields.estimated_fees,
            estimated_open_fee=trade_cost_fields.estimated_open_fee,
            estimated_close_fee=trade_cost_fields.estimated_close_fee,
            estimated_fixed_fees=trade_cost_fields.estimated_fixed_fees,
            estimated_spread_cost=trade_cost_fields.estimated_spread_cost,
            estimated_total_cost=trade_cost_fields.estimated_total_cost,
            estimated_total_cost_percent=trade_cost_fields.estimated_total_cost_percent,
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
        trade_cost_estimate: TradeCostEstimate,
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

        effective_breakeven_buffer_percent = (
            risk_profile.breakeven_buffer_percent
            + trade_cost_estimate.total_estimated_cost_percent
        )
        effective_breakeven_trigger_percent = max(
            risk_profile.breakeven_trigger_percent
            + trade_cost_estimate.total_estimated_cost_percent,
            effective_breakeven_buffer_percent,
        )
        trade_cost_fields = self._trade_cost_plan_fields(trade_cost_estimate)

        return TradePlan(
            approved=True,
            reason=signal.reason,
            symbol=snapshot.symbol,
            side=signal.action,
            amount=round(amount, 4),
            stop_loss=round(stop_loss, 5),
            take_profit=round(take_profit, 5),
            expected_gross_profit=trade_cost_fields.expected_gross_profit,
            expected_net_profit=trade_cost_fields.expected_net_profit,
            expected_net_profit_percent=trade_cost_fields.expected_net_profit_percent,
            required_min_expected_net_profit_amount=(
                trade_cost_fields.required_min_expected_net_profit_amount
            ),
            min_expected_net_profit_percent=trade_cost_fields.min_expected_net_profit_percent,
            estimated_fees=trade_cost_fields.estimated_fees,
            estimated_open_fee=trade_cost_fields.estimated_open_fee,
            estimated_close_fee=trade_cost_fields.estimated_close_fee,
            estimated_fixed_fees=trade_cost_fields.estimated_fixed_fees,
            estimated_spread_cost=trade_cost_fields.estimated_spread_cost,
            estimated_total_cost=trade_cost_fields.estimated_total_cost,
            estimated_total_cost_percent=trade_cost_fields.estimated_total_cost_percent,
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
            configured_breakeven_trigger_percent=round(risk_profile.breakeven_trigger_percent, 4),
            configured_breakeven_buffer_percent=round(risk_profile.breakeven_buffer_percent, 4),
            breakeven_trigger_percent=round(effective_breakeven_trigger_percent, 4),
            breakeven_buffer_percent=round(effective_breakeven_buffer_percent, 4),
            trailing_stop_enabled=risk_profile.trailing_stop_enabled,
            trailing_stop_trigger_percent=risk_profile.trailing_stop_trigger_percent,
            trailing_stop_distance_percent=risk_profile.trailing_stop_distance_percent,
        )

    def _trade_cost_plan_fields(
        self,
        trade_cost_estimate: TradeCostEstimate | None,
    ) -> TradeCostPlanFields:
        if trade_cost_estimate is None:
            return TradeCostPlanFields()

        return TradeCostPlanFields(
            expected_gross_profit=round(trade_cost_estimate.expected_gross_profit, 4),
            expected_net_profit=round(trade_cost_estimate.expected_net_profit, 4),
            expected_net_profit_percent=round(
                trade_cost_estimate.expected_net_profit_percent,
                4,
            ),
            required_min_expected_net_profit_amount=round(
                trade_cost_estimate.required_min_expected_net_profit_amount,
                4,
            ),
            min_expected_net_profit_percent=round(
                trade_cost_estimate.min_expected_net_profit_percent,
                4,
            ),
            estimated_fees=round(trade_cost_estimate.total_estimated_cost, 4),
            estimated_open_fee=round(trade_cost_estimate.open_fee, 4),
            estimated_close_fee=round(trade_cost_estimate.close_fee, 4),
            estimated_fixed_fees=round(trade_cost_estimate.fixed_fees, 4),
            estimated_spread_cost=round(trade_cost_estimate.spread_cost, 4),
            estimated_total_cost=round(trade_cost_estimate.total_estimated_cost, 4),
            estimated_total_cost_percent=round(
                trade_cost_estimate.total_estimated_cost_percent,
                4,
            ),
        )

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

    def _calculate_spread_percent(self, snapshot: MarketSnapshot) -> float:
        return calculate_spread_percent(snapshot)

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
