from app.config.settings import Settings
from app.execution.sl_tp_profile import EffectiveSlTpResolver
from app.execution.trade_candidate import TradeCandidate
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass, RiskProfile
from app.market.models import Candle, MarketSnapshot
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.risk.trade_cost_model import TradeCostConfig
from app.strategies.signals import Signal

SESSION_KEY = 'test-session'


def risk_profile(*, asset_class: AssetClass, max_position_size_percent: float = 100.0, take_profit_percent: float = 1.6, trade_cost: TradeCostConfig, breakeven_stop_enabled: bool = False, breakeven_trigger_percent: float = 1.0, breakeven_buffer_percent: float = 0.0) -> RiskProfile:
    return RiskProfile(
        asset_class=asset_class,
        max_position_size_percent=max_position_size_percent,
        stop_loss_percent=0.9,
        take_profit_percent=take_profit_percent,
        force_close_enabled=False,
        force_close_hour=23,
        force_close_minute=59,
        max_spread_percent=5.0,
        min_move_spread_ratio=0.0,
        dynamic_sl_tp_enabled=False,
        stop_loss_atr_multiplier=1.2,
        take_profit_atr_multiplier=2.0,
        min_stop_loss_percent=0.4,
        max_stop_loss_percent=1.5,
        min_take_profit_percent=0.8,
        max_take_profit_percent=3.0,
        breakeven_stop_enabled=breakeven_stop_enabled,
        breakeven_trigger_percent=breakeven_trigger_percent,
        breakeven_buffer_percent=breakeven_buffer_percent,
        trade_cost=trade_cost,
    )


def build_risk_manager(profile: RiskProfile) -> RiskManager:
    settings = Settings(EQUITY_US_SYMBOLS='AAPL', CRYPTO_SYMBOLS='BTC')
    return RiskManager(
        settings=settings,
        position_sizing_strategy=FixedPercentPositionSizing(),
        instrument_registry=InstrumentRegistry(settings, risk_profiles={profile.asset_class: profile}),
    )


def snapshot(symbol: str = 'AAPL', bid: float = 99.95, ask: float = 100.05) -> MarketSnapshot:
    return MarketSnapshot.now(symbol=symbol, bid=bid, ask=ask, last=100.0)


def buy_signal() -> Signal:
    return Signal(action='BUY', confidence=0.75, reason='test_buy')


def _candidate(signal: Signal, snapshot: MarketSnapshot) -> TradeCandidate:
    candle = Candle(symbol=snapshot.symbol, timeframe_seconds=60, open=snapshot.last, high=snapshot.last, low=snapshot.last, close=snapshot.last, volume=None, opened_at=snapshot.timestamp, closed_at=snapshot.timestamp)
    return TradeCandidate(symbol=snapshot.symbol, snapshot=snapshot, candle=candle, signal=signal, score=120.0, rank_reason='risk_manager_test')


def evaluate(risk_manager: RiskManager, signal: Signal, snapshot: MarketSnapshot, account_equity: float):
    effective_sl_tp = EffectiveSlTpResolver().resolve(candidate=_candidate(signal, snapshot), risk_profile=risk_manager.risk_profile_for(snapshot.symbol))
    return risk_manager.evaluate(signal=signal, snapshot=snapshot, account_equity=account_equity, session_key=SESSION_KEY, effective_sl_tp=effective_sl_tp)


def test_risk_manager_uses_dynamic_equity_trade_costs_and_net_breakeven():
    profile = risk_profile(asset_class=AssetClass.EQUITY_US, trade_cost=TradeCostConfig(open_fee_percent=0.15, close_fee_percent=0.15, include_spread_cost=True, min_expected_net_profit_percent=0.10), breakeven_stop_enabled=True, breakeven_trigger_percent=1.0, breakeven_buffer_percent=0.0)
    plan = evaluate(build_risk_manager(profile), buy_signal(), snapshot(), 1000.0)

    assert plan.approved
    assert plan.amount == 1000.0
    assert plan.expected_gross_profit == 16.0
    assert plan.expected_net_profit == 12.0
    assert plan.expected_net_profit_percent == 1.2
    assert plan.required_min_expected_net_profit_amount == 1.0
    assert plan.min_expected_net_profit_percent == 0.1
    assert plan.estimated_open_fee == 1.5
    assert plan.estimated_close_fee == 1.5
    assert plan.estimated_spread_cost == 1.0
    assert plan.estimated_total_cost == 4.0
    assert plan.estimated_fees == 4.0
    assert plan.estimated_total_cost_percent == 0.4
    assert plan.configured_breakeven_trigger_percent == 1.0
    assert plan.configured_breakeven_buffer_percent == 0.0
    assert plan.breakeven_trigger_percent == 1.4
    assert plan.breakeven_buffer_percent == 0.4


def test_risk_manager_rejects_trade_when_net_profit_percent_is_too_low():
    profile = risk_profile(asset_class=AssetClass.EQUITY_US, take_profit_percent=3.0, trade_cost=TradeCostConfig(open_fee_percent=1.0, close_fee_percent=1.0, include_spread_cost=False, min_expected_net_profit_percent=1.20))
    plan = evaluate(build_risk_manager(profile), buy_signal(), snapshot(bid=100.0, ask=100.0), 500.0)

    assert not plan.approved
    assert plan.reason == 'expected_profit_too_low_after_fees'
    assert plan.expected_gross_profit == 15.0
    assert plan.estimated_total_cost == 10.0
    assert plan.expected_net_profit == 5.0
    assert plan.expected_net_profit_percent == 1.0
    assert plan.required_min_expected_net_profit_amount == 6.0
    assert plan.min_expected_net_profit_percent == 1.2


def test_risk_manager_accepts_crypto_trade_when_net_percent_is_positive():
    profile = risk_profile(asset_class=AssetClass.CRYPTO, max_position_size_percent=100.0, take_profit_percent=3.0, trade_cost=TradeCostConfig(open_fee_percent=1.0, close_fee_percent=1.0, include_spread_cost=False, min_expected_net_profit_percent=0.10))
    plan = evaluate(build_risk_manager(profile), buy_signal(), snapshot(symbol='BTC', bid=100.0, ask=100.0), 747.0)

    assert plan.approved
    assert plan.amount == 747.0
    assert plan.expected_gross_profit == 22.41
    assert plan.estimated_total_cost == 14.94
    assert plan.expected_net_profit == 7.47
    assert plan.expected_net_profit_percent == 1.0
    assert plan.required_min_expected_net_profit_amount == 0.747
    assert plan.min_expected_net_profit_percent == 0.1


def test_risk_manager_uses_trade_cost_min_profit_percent():
    profile = risk_profile(asset_class=AssetClass.EQUITY_US, trade_cost=TradeCostConfig(open_fee_percent=0.15, close_fee_percent=0.15, include_spread_cost=True, min_expected_net_profit_percent=0.10))
    plan = evaluate(build_risk_manager(profile), buy_signal(), snapshot(), 1000.0)

    assert plan.approved
    assert plan.expected_net_profit == 12.0
    assert plan.expected_net_profit_percent == 1.2
    assert plan.required_min_expected_net_profit_amount == 1.0
    assert plan.min_expected_net_profit_percent == 0.1


def test_risk_manager_uses_net_breakeven_buffer_when_configured_buffer_is_positive():
    profile = risk_profile(asset_class=AssetClass.EQUITY_US, trade_cost=TradeCostConfig(open_fee_percent=0.15, close_fee_percent=0.15, include_spread_cost=False, min_expected_net_profit_percent=0.0), breakeven_stop_enabled=True, breakeven_trigger_percent=1.0, breakeven_buffer_percent=1.0)
    plan = evaluate(build_risk_manager(profile), buy_signal(), snapshot(bid=100.0, ask=100.0), 1000.0)

    assert plan.approved
    assert plan.estimated_total_cost_percent == 0.3
    assert plan.configured_breakeven_trigger_percent == 1.0
    assert plan.configured_breakeven_buffer_percent == 1.0
    assert plan.breakeven_trigger_percent == 1.3
    assert plan.breakeven_buffer_percent == 1.3
