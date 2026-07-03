from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass, RiskProfile
from app.market.models import MarketSnapshot
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.risk.trade_cost_model import TradeCostConfig
from app.strategies.signals import Signal


def risk_profile(
    *,
    asset_class: AssetClass,
    max_position_size_percent: float = 100.0,
    take_profit_percent: float = 1.6,
    min_expected_net_profit: float = 5.0,
    trade_cost: TradeCostConfig,
    breakeven_stop_enabled: bool = False,
    breakeven_trigger_percent: float = 1.0,
    breakeven_buffer_percent: float = 0.0,
) -> RiskProfile:
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
    settings = Settings()
    return RiskManager(
        settings=settings,
        position_sizing_strategy=FixedPercentPositionSizing(),
        instrument_registry=InstrumentRegistry(
            settings,
            risk_profiles={
                profile.asset_class: profile,
                AssetClass.UNKNOWN: profile,
            },
        ),
    )


def snapshot(symbol: str = 'AAPL', bid: float = 99.95, ask: float = 100.05) -> MarketSnapshot:
    return MarketSnapshot.now(symbol=symbol, bid=bid, ask=ask, last=100.0)


def buy_signal() -> Signal:
    return Signal(action='BUY', confidence=0.75, reason='test_buy')


def test_risk_manager_uses_dynamic_equity_trade_costs_and_net_breakeven():
    profile = risk_profile(
        asset_class=AssetClass.UNKNOWN,
        trade_cost=TradeCostConfig(
            open_fee_percent=0.15,
            close_fee_percent=0.15,
            include_spread_cost=True,
            min_expected_net_profit=5.0,
        ),
        breakeven_stop_enabled=True,
        breakeven_trigger_percent=1.0,
        breakeven_buffer_percent=0.0,
    )
    risk_manager = build_risk_manager(profile)

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot(),
        account_equity=1000.0,
    )

    assert plan.approved
    assert plan.amount == 1000.0
    assert plan.expected_gross_profit == 16.0
    assert plan.estimated_open_fee == 1.5
    assert plan.estimated_close_fee == 1.5
    assert plan.estimated_spread_cost == 1.0
    assert plan.estimated_total_cost == 4.0
    assert plan.estimated_fees == 4.0
    assert plan.estimated_total_cost_percent == 0.4
    assert plan.expected_net_profit == 12.0
    assert plan.min_expected_net_profit == 5.0
    assert plan.configured_breakeven_trigger_percent == 1.0
    assert plan.configured_breakeven_buffer_percent == 0.0
    assert plan.breakeven_trigger_percent == 1.4
    assert plan.breakeven_buffer_percent == 0.4


def test_risk_manager_rejects_trade_when_dynamic_net_profit_is_too_low():
    profile = risk_profile(
        asset_class=AssetClass.UNKNOWN,
        take_profit_percent=3.0,
        trade_cost=TradeCostConfig(
            open_fee_percent=1.0,
            close_fee_percent=1.0,
            include_spread_cost=False,
            min_expected_net_profit=8.0,
        ),
    )
    risk_manager = build_risk_manager(profile)

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot(bid=100.0, ask=100.0),
        account_equity=500.0,
    )

    assert not plan.approved
    assert plan.reason == 'expected_profit_too_low_after_fees'
    assert plan.expected_gross_profit == 15.0
    assert plan.estimated_total_cost == 10.0
    assert plan.expected_net_profit == 5.0
    assert plan.min_expected_net_profit == 8.0


def test_risk_manager_uses_trade_cost_min_profit_when_enabled():
    profile = risk_profile(
        asset_class=AssetClass.UNKNOWN,
        min_expected_net_profit=999.0,
        trade_cost=TradeCostConfig(
            open_fee_percent=0.15,
            close_fee_percent=0.15,
            include_spread_cost=True,
            min_expected_net_profit=5.0,
        ),
    )
    risk_manager = build_risk_manager(profile)

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot(),
        account_equity=1000.0,
    )

    assert plan.approved
    assert plan.expected_net_profit == 12.0
    assert plan.min_expected_net_profit == 5.0


def test_risk_manager_uses_net_breakeven_buffer_when_configured_buffer_is_positive():
    profile = risk_profile(
        asset_class=AssetClass.UNKNOWN,
        trade_cost=TradeCostConfig(
            open_fee_percent=0.15,
            close_fee_percent=0.15,
            include_spread_cost=False,
            min_expected_net_profit=0.0,
        ),
        breakeven_stop_enabled=True,
        breakeven_trigger_percent=1.0,
        breakeven_buffer_percent=1.0,
    )
    risk_manager = build_risk_manager(profile)

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot(bid=100.0, ask=100.0),
        account_equity=1000.0,
    )

    assert plan.approved
    assert plan.estimated_total_cost_percent == 0.3
    assert plan.configured_breakeven_trigger_percent == 1.0
    assert plan.configured_breakeven_buffer_percent == 1.0
    assert plan.breakeven_trigger_percent == 1.3
    assert plan.breakeven_buffer_percent == 1.3
