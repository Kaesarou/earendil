from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.config.settings import Settings
from app.execution.candidate_economics import CandidateEconomicsEstimator
from app.execution.trade_candidate import TradeCandidate
from app.instruments.base_configs import EQUITY_US_CONFIG
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass
from app.market.models import Candle, MarketSnapshot
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.strategies.signals import Signal

SESSION_KEY = 'EQUITY_US:test-session'


def make_candidate(action: str) -> TradeCandidate:
    now = datetime(2026, 7, 4, 18, 0, tzinfo=timezone.utc)
    snapshot = MarketSnapshot(
        symbol='AAPL',
        bid=99.95,
        ask=100.05,
        last=100.0,
        timestamp=now,
    )
    candle = Candle(
        symbol='AAPL',
        timeframe_seconds=60,
        open=99.0,
        high=101.0,
        low=98.5,
        close=100.0,
        volume=None,
        opened_at=now,
        closed_at=now,
    )
    signal = Signal(
        action=action,
        confidence=0.8,
        reason='test_signal',
    )

    return TradeCandidate(
        symbol='AAPL',
        snapshot=snapshot,
        candle=candle,
        signal=signal,
        score=120.0,
        rank_reason='test',
        session_key=SESSION_KEY,
    )


def build_instrument_registry() -> InstrumentRegistry:
    settings = Settings(EQUITY_US_SYMBOLS='AAPL')
    risk_profile = replace(
        EQUITY_US_CONFIG.risk,
        force_close_enabled=False,
    )
    return InstrumentRegistry(
        settings,
        risk_profiles={AssetClass.EQUITY_US: risk_profile},
    )


@pytest.mark.parametrize('action', ['BUY', 'SELL'])
def test_candidate_economics_matches_risk_manager_trade_costs(action: str):
    settings = Settings(EQUITY_US_SYMBOLS='AAPL')
    instrument_registry = build_instrument_registry()
    position_sizing_strategy = FixedPercentPositionSizing()
    estimator = CandidateEconomicsEstimator(
        position_sizing_strategy=position_sizing_strategy,
        instrument_registry=instrument_registry,
    )
    risk_manager = RiskManager(
        settings=settings,
        position_sizing_strategy=position_sizing_strategy,
        instrument_registry=instrument_registry,
    )
    candidate = make_candidate(action)

    evaluated_candidate = estimator.evaluate(
        candidate=candidate,
        account_equity=100000.0,
    )
    plan = risk_manager.evaluate(
        signal=candidate.signal,
        snapshot=candidate.snapshot,
        account_equity=100000.0,
        session_key=candidate.session_key,
    )

    assert plan.approved
    assert plan.side == action
    assert plan.amount == pytest.approx(evaluated_candidate.economics.position_value)
    assert plan.expected_gross_profit == pytest.approx(
        evaluated_candidate.economics.expected_gross_profit,
    )
    assert plan.expected_net_profit == pytest.approx(
        evaluated_candidate.economics.expected_net_profit,
    )
    assert plan.expected_net_profit_percent == pytest.approx(
        evaluated_candidate.economics.expected_net_profit_percent,
    )
    assert plan.estimated_total_cost == pytest.approx(
        evaluated_candidate.economics.estimated_total_cost,
    )
    assert plan.estimated_total_cost_percent == pytest.approx(
        evaluated_candidate.economics.estimated_total_cost_percent,
    )
    assert plan.min_expected_net_profit_percent == pytest.approx(
        evaluated_candidate.economics.min_expected_net_profit_percent,
    )
    assert plan.required_min_expected_net_profit_amount == pytest.approx(
        evaluated_candidate.economics.required_min_expected_net_profit_amount,
    )


def test_risk_manager_builds_sell_trade_plan_with_short_side_price_levels():
    settings = Settings(EQUITY_US_SYMBOLS='AAPL')
    instrument_registry = build_instrument_registry()
    risk_manager = RiskManager(
        settings=settings,
        position_sizing_strategy=FixedPercentPositionSizing(),
        instrument_registry=instrument_registry,
    )
    candidate = make_candidate('SELL')

    plan = risk_manager.evaluate(
        signal=candidate.signal,
        snapshot=candidate.snapshot,
        account_equity=100000.0,
        session_key=candidate.session_key,
    )

    assert plan.approved
    assert plan.side == 'SELL'
    assert plan.stop_loss == 100.9
    assert plan.take_profit == 98.4
    assert plan.stop_loss > candidate.snapshot.last
    assert plan.take_profit < candidate.snapshot.last
