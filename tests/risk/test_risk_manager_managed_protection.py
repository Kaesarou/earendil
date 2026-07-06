from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass, InstrumentProfile, RiskProfile
from app.market.models import MarketSnapshot
from app.risk.position_sizing import FixedPercentPositionSizingStrategy
from app.risk.risk_manager import RiskManager
from app.risk.trade_cost_model import TradeCostConfig
from app.strategies.signals import Signal

SESSION_KEY = 'test-session'


class TestInstrumentRegistry(InstrumentRegistry):
    def __init__(self, risk_profile: RiskProfile):
        self.risk_profile = risk_profile

    def resolve(self, symbol: str) -> InstrumentProfile:
        return InstrumentProfile(symbol=symbol, asset_class=AssetClass.EQUITY_US)

    def risk_profile_for(self, symbol: str) -> RiskProfile:
        return self.risk_profile


def risk_profile() -> RiskProfile:
    return RiskProfile(
        asset_class=AssetClass.EQUITY_US,
        max_position_size_percent=1.0,
        stop_loss_percent=0.9,
        take_profit_percent=1.6,
        force_close_enabled=False,
        force_close_hour=21,
        force_close_minute=55,
        max_spread_percent=1.0,
        min_move_spread_ratio=0.0,
        dynamic_sl_tp_enabled=False,
        stop_loss_atr_multiplier=1.0,
        take_profit_atr_multiplier=2.0,
        min_stop_loss_percent=0.0,
        max_stop_loss_percent=2.0,
        min_take_profit_percent=0.0,
        max_take_profit_percent=3.0,
        breakeven_stop_enabled=True,
        breakeven_trigger_percent=0.6,
        breakeven_buffer_percent=0.05,
        trailing_stop_enabled=True,
        trailing_stop_trigger_percent=1.0,
        trailing_stop_distance_percent=0.45,
        trailing_stop_net_buffer_percent=0.1,
        trade_cost=TradeCostConfig(open_fee_percent=0.15, close_fee_percent=0.15, include_spread_cost=False),
    )


def build_risk_manager(profile: RiskProfile) -> RiskManager:
    return RiskManager(
        settings=Settings(MAX_OPEN_POSITIONS=10, MAX_OPEN_POSITIONS_PER_SYMBOL=10, MAX_TRADES_PER_SESSION=10),
        position_sizing_strategy=FixedPercentPositionSizingStrategy(),
        instrument_registry=TestInstrumentRegistry(profile),
    )


def test_risk_manager_keeps_breakeven_cost_aware_and_propagates_trailing_net_buffer():
    manager = build_risk_manager(risk_profile())

    plan = manager.evaluate(
        signal=Signal(action='BUY', confidence=0.8, reason='test'),
        snapshot=MarketSnapshot.now(symbol='AAPL', bid=99.95, ask=100.05, last=100.0),
        account_equity=100_000.0,
        session_key=SESSION_KEY,
    )

    assert plan.approved is True
    assert plan.configured_breakeven_trigger_percent == 0.6
    assert plan.configured_breakeven_buffer_percent == 0.05
    assert plan.estimated_total_cost_percent == 0.3
    assert plan.breakeven_trigger_percent == 0.9
    assert plan.breakeven_buffer_percent == 0.35
    assert plan.trailing_stop_trigger_percent == 1.0
    assert plan.trailing_stop_distance_percent == 0.45
    assert plan.trailing_stop_net_buffer_percent == 0.1
