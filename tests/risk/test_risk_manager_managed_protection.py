from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass, InstrumentProfile, RiskProfile
from app.market.models import MarketSnapshot
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.risk.trade_cost_model import TradeCostConfig
from app.strategies.signals import Signal


class StubInstrumentRegistry(InstrumentRegistry):
    def __init__(self, risk_profile: RiskProfile):
        self.risk_profile = risk_profile

    def resolve(self, symbol: str) -> InstrumentProfile:
        return InstrumentProfile(symbol=symbol, asset_class=AssetClass.EQUITY_US)

    def risk_profile_for(self, symbol: str) -> RiskProfile:
        return self.risk_profile


def risk_profile() -> RiskProfile:
    return RiskProfile(
        asset_class=AssetClass.EQUITY_US,
        profile_key='us_test_fixed_v1',
        max_position_size_percent=1.0,
        stop_loss_percent=0.7,
        take_profit_percent=1.2,
        force_close_enabled=False,
        force_close_hour=21,
        force_close_minute=55,
        max_spread_percent=1.0,
        min_move_spread_ratio=0.0,
        breakeven_stop_enabled=True,
        breakeven_trigger_percent=0.6,
        breakeven_buffer_percent=0.05,
        trailing_stop_enabled=True,
        trailing_stop_trigger_percent=1.0,
        trailing_stop_distance_percent=0.45,
        trailing_stop_net_buffer_percent=0.1,
        trade_cost=TradeCostConfig(
            open_fee_percent=0.15,
            close_fee_percent=0.15,
            include_spread_cost=False,
        ),
    )


def test_risk_manager_propagates_net_breakeven_and_trailing_contract():
    manager = RiskManager(
        settings=Settings(
            MAX_OPEN_POSITIONS=10,
            MAX_OPEN_POSITIONS_PER_SYMBOL=10,
            MAX_TRADES_PER_SESSION=10,
        ),
        position_sizing_strategy=FixedPercentPositionSizing(),
        instrument_registry=StubInstrumentRegistry(risk_profile()),
    )
    plan = manager.evaluate(
        signal=Signal(action='BUY', setup_quality=0.8, reason='test'),
        snapshot=MarketSnapshot.now(
            symbol='AAPL',
            bid=99.95,
            ask=100.05,
            last=100.0,
        ),
        account_equity=100_000.0,
        session_key='test-session',
    )

    assert plan.approved is True
    assert plan.profile_key == 'us_test_fixed_v1'
    assert plan.estimated_total_cost_percent == 0.3
    assert plan.configured_breakeven_trigger_percent == 0.6
    assert plan.configured_breakeven_buffer_percent == 0.05
    assert plan.breakeven_trigger_percent == 0.6
    assert plan.breakeven_buffer_percent == 0.05
    assert plan.trailing_stop_trigger_percent == 1.0
    assert plan.trailing_stop_distance_percent == 0.45
    assert plan.trailing_stop_net_buffer_percent == 0.1
