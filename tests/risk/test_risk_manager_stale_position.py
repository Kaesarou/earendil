from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.market.models import MarketSnapshot
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.strategies.signals import Signal

SESSION_KEY = 'EQUITY_US:test-session'


def test_risk_manager_adds_stale_position_settings_to_trade_plan():
    settings = Settings(EQUITY_US_SYMBOLS='AAPL')
    risk_manager = RiskManager(
        settings=settings,
        position_sizing_strategy=FixedPercentPositionSizing(),
        instrument_registry=InstrumentRegistry(settings),
    )

    plan = risk_manager.evaluate(
        signal=Signal(action='BUY', confidence=0.8, reason='test_buy'),
        snapshot=MarketSnapshot.now(symbol='AAPL', bid=99.95, ask=100.05, last=100.0),
        account_equity=100000.0,
        session_key=SESSION_KEY,
    )

    assert plan.approved
    assert plan.stale_position_enabled
    assert plan.stale_position_max_age_minutes == 60
    assert plan.stale_position_min_favorable_move_percent == 0.35
    assert plan.stale_position_buffer_percent == 0.10
    assert plan.estimated_total_cost_percent is not None
