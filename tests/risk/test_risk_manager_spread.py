from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass, RiskProfile
from app.market.models import MarketSnapshot
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.risk.trade_cost_model import TradeCostConfig
from app.strategies.signals import Signal

SESSION_KEY = 'test-session'


def build_risk_manager_with_spread_limit() -> RiskManager:
    settings = Settings(EQUITY_US_SYMBOLS='AAPL')
    risk_profile = RiskProfile(
        asset_class=AssetClass.EQUITY_US,
        max_position_size_percent=40.0,
        stop_loss_percent=0.3,
        take_profit_percent=0.5,
        force_close_enabled=False,
        force_close_hour=23,
        force_close_minute=59,
        max_spread_percent=0.5,
        min_move_spread_ratio=4.0,
        dynamic_sl_tp_enabled=False,
        stop_loss_atr_multiplier=1.5,
        take_profit_atr_multiplier=2.5,
        min_stop_loss_percent=0.0,
        max_stop_loss_percent=0.0,
        min_take_profit_percent=0.0,
        max_take_profit_percent=0.0,
        trade_cost=TradeCostConfig(include_spread_cost=False),
    )

    return RiskManager(
        settings=settings,
        position_sizing_strategy=FixedPercentPositionSizing(),
        instrument_registry=InstrumentRegistry(
            settings,
            risk_profiles={AssetClass.EQUITY_US: risk_profile},
        ),
    )


def buy_signal() -> Signal:
    return Signal(
        action='BUY',
        confidence=0.65,
        reason='test_buy',
    )


def snapshot(
    *,
    bid: float,
    ask: float,
    last: float,
) -> MarketSnapshot:
    return MarketSnapshot.now(
        symbol='AAPL',
        bid=bid,
        ask=ask,
        last=last,
    )


def test_risk_manager_treats_invalid_spread_as_too_high():
    risk_manager = build_risk_manager_with_spread_limit()

    plan = risk_manager.evaluate(
        signal=buy_signal(),
        snapshot=snapshot(bid=100.1, ask=99.9, last=100.0),
        account_equity=100.0,
        session_key=SESSION_KEY,
    )

    assert not plan.approved
    assert plan.reason == 'spread_too_high'
    assert plan.spread_percent == 100.0
    assert plan.max_spread_percent == 0.5
    assert plan.min_required_move_percent == 400.0
