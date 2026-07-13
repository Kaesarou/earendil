from datetime import datetime, timezone

from app.config.settings import Settings
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass
from app.market.models import Candle, MarketSnapshot
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.runtime.symbol_flow import process_closed_candle
from app.runtime.trading_session_window import TradingSessionDecision
from app.strategies.signals import Signal


class FakeJournal:
    def __init__(self):
        self.events = []

    def write(self, event_type, payload):
        self.events.append((event_type, payload))


class BuyStrategy:
    def on_candle(self, candle):
        return Signal(action='BUY', setup_quality=0.8, reason='test_buy')


def build_risk_manager() -> RiskManager:
    settings = Settings(EQUITY_US_SYMBOLS='AAPL')
    return RiskManager(
        settings=settings,
        position_sizing_strategy=FixedPercentPositionSizing(),
        instrument_registry=InstrumentRegistry(settings),
    )


def test_process_closed_candle_blocks_candidate_when_new_entries_are_not_allowed():
    now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
    trade_journal = FakeJournal()
    decision = TradingSessionDecision(
        asset_class=AssetClass.EQUITY_US,
        session_active=True,
        session_24_7=False,
        collect_snapshots=True,
        new_entries_allowed=False,
        force_close_required=False,
        reason='too_close_to_session_end',
        session_start_time=None,
        session_end_time=None,
        time_until_session_end_minutes=30.0,
        session_key='test-session',
    )

    candidate = process_closed_candle(
        symbol='AAPL',
        snapshot=MarketSnapshot(symbol='AAPL', bid=99.9, ask=100.1, last=100.0, timestamp=now),
        closed_candle=Candle(
            symbol='AAPL',
            timeframe_seconds=60,
            open=99.0,
            high=101.0,
            low=98.0,
            close=100.0,
            volume=None,
            opened_at=now,
            closed_at=now,
        ),
        strategy=BuyStrategy(),
        risk_manager=build_risk_manager(),
        trade_journal=trade_journal,
        candle_journal=FakeJournal(),
        session_decision=decision,
    )

    assert candidate is None
    assert trade_journal.events[-1][1]['trade_plan'].reason == 'too_close_to_session_end'
