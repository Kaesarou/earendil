from collections import defaultdict
from dataclasses import dataclass, replace

from app.config.settings import Settings
from app.execution.sl_tp_profile import EffectiveSlTp
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import InstrumentProfile, RiskProfile
from app.market.models import MarketSnapshot
from app.risk.models import TradePlan
from app.risk.position_sizing import PositionSizingStrategy
from app.risk.trade_cost_model import TradeCostEstimate, TradeCostModel
from app.strategies.signals import Signal
from app.utils.commons import normalize_symbol, spread_percent as calculate_spread_percent


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
    def __init__(self, settings: Settings, position_sizing_strategy: PositionSizingStrategy, instrument_registry: InstrumentRegistry, trade_cost_model: TradeCostModel | None = None):
        self.settings = settings
        self.position_sizing_strategy = position_sizing_strategy
        self.instrument_registry = instrument_registry
        self.trade_cost_model = trade_cost_model or TradeCostModel()
        self.trades_by_session: dict[str, int] = defaultdict(int)
        self.open_positions = 0
        self.open_positions_by_symbol: dict[str, int] = defaultdict(int)

    def evaluate(self, signal: Signal, snapshot: MarketSnapshot, account_equity: float, session_key: str, effective_sl_tp: EffectiveSlTp) -> TradePlan:
        risk_profile = self.risk_profile_for(snapshot.symbol)
        spread_percent = self._calculate_spread_percent(snapshot)
        expected_move_percent = effective_sl_tp.take_profit_percent
        min_required_move_percent = self._calculate_min_required_move_percent(spread_percent, risk_profile)
        rejection_reason = self._rejection_reason(signal, snapshot.symbol, risk_profile, spread_percent, session_key)
        if rejection_reason is not None:
            return self._rejected_plan(rejection_reason, signal, snapshot, risk_profile, effective_sl_tp, spread_percent, expected_move_percent, min_required_move_percent)

        amount = self.position_sizing_strategy.calculate_amount(account_equity=account_equity, risk_profile=risk_profile)
        if amount <= 0:
            return self._rejected_plan('invalid_position_amount', signal, snapshot, risk_profile, effective_sl_tp, spread_percent, expected_move_percent, min_required_move_percent)

        trade_cost_estimate = self.trade_cost_model.estimate(
            position_value=amount,
            expected_move_percent=expected_move_percent,
            spread_percent=spread_percent,
            config=risk_profile.trade_cost,
        )
        if trade_cost_estimate.expected_net_profit_percent < trade_cost_estimate.min_expected_net_profit_percent:
            return self._rejected_plan(
                'expected_profit_too_low_after_fees', signal, snapshot, risk_profile, effective_sl_tp,
                spread_percent, expected_move_percent, min_required_move_percent, amount, trade_cost_estimate
            )
        return self._build_trade_plan(signal, snapshot, amount, trade_cost_estimate, risk_profile, effective_sl_tp, spread_percent, expected_move_percent, min_required_move_percent)

    def adjust_trade_plan_to_entry_price(self, *, trade_plan: TradePlan, entry_price: float) -> TradePlan:
        if not trade_plan.approved:
            raise ValueError(f'Cannot adjust rejected trade plan: {trade_plan}')
        if entry_price <= 0:
            raise ValueError(f'Cannot adjust trade plan with invalid entry_price: {entry_price}')
        if trade_plan.side not in ('BUY', 'SELL'):
            raise ValueError(f'Unsupported trade plan side for entry adjustment: {trade_plan.side}')
        if trade_plan.effective_stop_loss_percent is None:
            raise ValueError(f'Cannot adjust trade plan without effective_stop_loss_percent: {trade_plan}')
        if trade_plan.effective_take_profit_percent is None:
            raise ValueError(f'Cannot adjust trade plan without effective_take_profit_percent: {trade_plan}')

        if trade_plan.side == 'BUY':
            stop_loss = entry_price * (1 - trade_plan.effective_stop_loss_percent / 100)
            take_profit = entry_price * (1 + trade_plan.effective_take_profit_percent / 100)
        else:
            stop_loss = entry_price * (1 + trade_plan.effective_stop_loss_percent / 100)
            take_profit = entry_price * (1 - trade_plan.effective_take_profit_percent / 100)

        return replace(trade_plan, stop_loss=round(stop_loss, 5), take_profit=round(take_profit, 5))

    def instrument_profile_for(self, symbol: str) -> InstrumentProfile:
        return self.instrument_registry.resolve(symbol)

    def risk_profile_for(self, symbol: str) -> RiskProfile:
        return self.instrument_registry.risk_profile_for(symbol)

    def record_open_position(self, symbol: str, session_key: str) -> None:
        normalized_symbol = normalize_symbol(symbol)
        self.open_positions += 1
        self.open_positions_by_symbol[normalized_symbol] += 1
        self.trades_by_session[session_key] += 1

    def restore_open_position(self, symbol: str) -> None:
        normalized_symbol = normalize_symbol(symbol)
        self.open_positions += 1
        self.open_positions_by_symbol[normalized_symbol] += 1

    def record_close_position(self, symbol: str) -> None:
        normalized_symbol = normalize_symbol(symbol)
        self.open_positions = max(0, self.open_positions - 1)
        next_count = max(0, self.open_positions_by_symbol.get(normalized_symbol, 0) - 1)
        if next_count == 0:
            self.open_positions_by_symbol.pop(normalized_symbol, None)
        else:
            self.open_positions_by_symbol[normalized_symbol] = next_count

    def reset_session_trades(self, session_key: str) -> None:
        self.trades_by_session.pop(session_key, None)

    def trades_for_session(self, session_key: str) -> int:
        return self.trades_by_session.get(session_key, 0)

    def _rejection_reason(self, signal: Signal, symbol: str, risk_profile: RiskProfile, spread_percent: float | None, session_key: str) -> str | None:
        if signal.action == 'HOLD':
            return signal.reason
        if signal.action not in ('BUY', 'SELL'):
            return f'unsupported_signal_{signal.action}'
        if self.open_positions >= self.settings.max_open_positions:
            return 'max_open_positions_reached'
        normalized_symbol = normalize_symbol(symbol)
        if self.open_positions_by_symbol.get(normalized_symbol, 0) >= self.settings.max_open_positions_per_symbol:
            return 'max_open_positions_per_symbol_reached'
        if self.trades_by_session[session_key] >= self.settings.max_trades_per_session:
            return 'max_trades_per_session_reached'
        if spread_percent is not None and risk_profile.max_spread_percent > 0 and spread_percent > risk_profile.max_spread_percent:
            return 'spread_too_high'
        return None

    def _rejected_plan(self, reason: str, signal: Signal, snapshot: MarketSnapshot, risk_profile: RiskProfile, effective_sl_tp: EffectiveSlTp, spread_percent: float | None, expected_move_percent: float, min_required_move_percent: float | None, amount: float | None = None, trade_cost_estimate: TradeCostEstimate | None = None) -> TradePlan:
        fields = self._trade_cost_plan_fields(trade_cost_estimate)
        return TradePlan(
            approved=False, reason=reason, symbol=snapshot.symbol, side=signal.action,
            amount=self._round_optional(amount), expected_gross_profit=fields.expected_gross_profit,
            expected_net_profit=fields.expected_net_profit, expected_net_profit_percent=fields.expected_net_profit_percent,
            required_min_expected_net_profit_amount=fields.required_min_expected_net_profit_amount,
            min_expected_net_profit_percent=fields.min_expected_net_profit_percent,
            estimated_fees=fields.estimated_fees, estimated_open_fee=fields.estimated_open_fee,
            estimated_close_fee=fields.estimated_close_fee, estimated_fixed_fees=fields.estimated_fixed_fees,
            estimated_spread_cost=fields.estimated_spread_cost, estimated_total_cost=fields.estimated_total_cost,
            estimated_total_cost_percent=fields.estimated_total_cost_percent, spread_percent=self._round_optional(spread_percent),
            max_spread_percent=risk_profile.max_spread_percent, expected_move_percent=round(expected_move_percent, 4),
            min_required_move_percent=self._round_optional(min_required_move_percent), min_move_spread_ratio=risk_profile.min_move_spread_ratio,
            atr_percent=self._round_optional(effective_sl_tp.atr_percent), dynamic_sl_tp_enabled=effective_sl_tp.dynamic_sl_tp_enabled,
            sl_tp_mode=effective_sl_tp.mode, sl_tp_source=effective_sl_tp.source,
            effective_stop_loss_percent=round(effective_sl_tp.stop_loss_percent, 4), effective_take_profit_percent=round(effective_sl_tp.take_profit_percent, 4),
        )

    def _build_trade_plan(self, signal: Signal, snapshot: MarketSnapshot, amount: float, trade_cost_estimate: TradeCostEstimate, risk_profile: RiskProfile, effective_sl_tp: EffectiveSlTp, spread_percent: float | None, expected_move_percent: float, min_required_move_percent: float | None) -> TradePlan:
        if signal.action == 'BUY':
            stop_loss = snapshot.last * (1 - effective_sl_tp.stop_loss_percent / 100)
            take_profit = snapshot.last * (1 + effective_sl_tp.take_profit_percent / 100)
        elif signal.action == 'SELL':
            stop_loss = snapshot.last * (1 + effective_sl_tp.stop_loss_percent / 100)
            take_profit = snapshot.last * (1 - effective_sl_tp.take_profit_percent / 100)
        else:
            raise ValueError(f'Unsupported signal action for trade plan: {signal.action}')

        buffer_percent = risk_profile.breakeven_buffer_percent + trade_cost_estimate.total_estimated_cost_percent
        trigger_percent = max(risk_profile.breakeven_trigger_percent + trade_cost_estimate.total_estimated_cost_percent, buffer_percent)
        fields = self._trade_cost_plan_fields(trade_cost_estimate)
        return TradePlan(
            approved=True, reason=signal.reason, symbol=snapshot.symbol, side=signal.action, amount=round(amount, 4),
            stop_loss=round(stop_loss, 5), take_profit=round(take_profit, 5),
            expected_gross_profit=fields.expected_gross_profit, expected_net_profit=fields.expected_net_profit,
            expected_net_profit_percent=fields.expected_net_profit_percent,
            required_min_expected_net_profit_amount=fields.required_min_expected_net_profit_amount,
            min_expected_net_profit_percent=fields.min_expected_net_profit_percent,
            estimated_fees=fields.estimated_fees, estimated_open_fee=fields.estimated_open_fee,
            estimated_close_fee=fields.estimated_close_fee, estimated_fixed_fees=fields.estimated_fixed_fees,
            estimated_spread_cost=fields.estimated_spread_cost, estimated_total_cost=fields.estimated_total_cost,
            estimated_total_cost_percent=fields.estimated_total_cost_percent, spread_percent=self._round_optional(spread_percent),
            max_spread_percent=risk_profile.max_spread_percent, expected_move_percent=round(expected_move_percent, 4),
            min_required_move_percent=self._round_optional(min_required_move_percent), min_move_spread_ratio=risk_profile.min_move_spread_ratio,
            atr_percent=self._round_optional(effective_sl_tp.atr_percent), dynamic_sl_tp_enabled=effective_sl_tp.dynamic_sl_tp_enabled,
            sl_tp_mode=effective_sl_tp.mode, sl_tp_source=effective_sl_tp.source,
            effective_stop_loss_percent=round(effective_sl_tp.stop_loss_percent, 4), effective_take_profit_percent=round(effective_sl_tp.take_profit_percent, 4),
            breakeven_stop_enabled=risk_profile.breakeven_stop_enabled,
            configured_breakeven_trigger_percent=round(risk_profile.breakeven_trigger_percent, 4),
            configured_breakeven_buffer_percent=round(risk_profile.breakeven_buffer_percent, 4),
            breakeven_trigger_percent=round(trigger_percent, 4), breakeven_buffer_percent=round(buffer_percent, 4),
            trailing_stop_enabled=risk_profile.trailing_stop_enabled,
            trailing_stop_trigger_percent=risk_profile.trailing_stop_trigger_percent,
            trailing_stop_distance_percent=risk_profile.trailing_stop_distance_percent,
            trailing_stop_net_buffer_percent=risk_profile.trailing_stop_net_buffer_percent,
            stale_position_enabled=risk_profile.stale_position.enabled,
            stale_position_max_age_minutes=risk_profile.stale_position.max_age_minutes,
            stale_position_min_favorable_move_percent=risk_profile.stale_position.min_favorable_move_percent,
            stale_position_buffer_percent=risk_profile.stale_position.buffer_percent,
        )

    def _trade_cost_plan_fields(self, trade_cost_estimate: TradeCostEstimate | None) -> TradeCostPlanFields:
        if trade_cost_estimate is None:
            return TradeCostPlanFields()
        return TradeCostPlanFields(
            expected_gross_profit=round(trade_cost_estimate.expected_gross_profit, 4),
            expected_net_profit=round(trade_cost_estimate.expected_net_profit, 4),
            expected_net_profit_percent=round(trade_cost_estimate.expected_net_profit_percent, 4),
            required_min_expected_net_profit_amount=round(trade_cost_estimate.required_min_expected_net_profit_amount, 4),
            min_expected_net_profit_percent=round(trade_cost_estimate.min_expected_net_profit_percent, 4),
            estimated_fees=round(trade_cost_estimate.total_estimated_cost, 4),
            estimated_open_fee=round(trade_cost_estimate.open_fee, 4),
            estimated_close_fee=round(trade_cost_estimate.close_fee, 4),
            estimated_fixed_fees=round(trade_cost_estimate.fixed_fees, 4),
            estimated_spread_cost=round(trade_cost_estimate.spread_cost, 4),
            estimated_total_cost=round(trade_cost_estimate.total_estimated_cost, 4),
            estimated_total_cost_percent=round(trade_cost_estimate.total_estimated_cost_percent, 4),
        )

    def _calculate_spread_percent(self, snapshot: MarketSnapshot) -> float:
        return calculate_spread_percent(snapshot)

    def _calculate_min_required_move_percent(self, spread_percent: float | None, risk_profile: RiskProfile) -> float | None:
        return None if spread_percent is None else spread_percent * risk_profile.min_move_spread_ratio

    def _round_optional(self, value: float | None) -> float | None:
        return None if value is None else round(value, 4)
