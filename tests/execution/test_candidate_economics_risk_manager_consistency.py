from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.config.settings import Settings
from app.execution.candidate_economics import CandidateEconomicsEstimator
from app.execution.scoring.tp_feasibility import CandidateTpFeasibilityEvaluator
from app.execution.trade_candidate import TradeCandidate
from app.instruments.base_configs import EQUITY_US_CONFIG
from app.instruments.instrument_registry import InstrumentRegistry
from app.instruments.models import AssetClass, RiskProfile
from app.market.models import Candle, MarketSnapshot
from app.risk.position_sizing import FixedPercentPositionSizing
from app.risk.risk_manager import RiskManager
from app.strategies.signals import Signal

SESSION_KEY = 'EQUITY_US:test-session'


def make_candidate(action: str, metadata: dict | None = None) -> TradeCandidate:
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
        metadata=metadata,
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


def build_instrument_registry(risk_profile: RiskProfile | None = None) -> InstrumentRegistry:
    settings = Settings(EQUITY_US_SYMBOLS='AAPL')
    actual_risk_profile = risk_profile or replace(
        EQUITY_US_CONFIG.risk,
        force_close_enabled=False,
    )
    return InstrumentRegistry(
        settings,
        risk_profiles={AssetClass.EQUITY_US: actual_risk_profile},
    )


def dynamic_us_risk_profile() -> RiskProfile:
    return replace(
        EQUITY_US_CONFIG.risk,
        force_close_enabled=False,
        dynamic_sl_tp_enabled=True,
        stop_loss_atr_multiplier=1.5,
        take_profit_atr_multiplier=2.5,
        min_stop_loss_percent=0.5,
        max_stop_loss_percent=2.0,
        min_take_profit_percent=1.0,
        max_take_profit_percent=4.0,
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


def test_effective_sl_tp_is_shared_across_economics_feasibility_and_risk_plan():
    settings = Settings(EQUITY_US_SYMBOLS='AAPL')
    risk_profile = dynamic_us_risk_profile()
    instrument_registry = build_instrument_registry(risk_profile)
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
    candidate = make_candidate(
        'BUY',
        metadata={
            'atr_percent': 0.8,
            'snapshot_momentum_percent': 0.5,
            'session_move_percent': 0.3,
        },
    )

    evaluated_candidate = estimator.evaluate(
        candidate=candidate,
        account_equity=100000.0,
    )
    scored_candidate = CandidateTpFeasibilityEvaluator().evaluate(
        evaluated_candidate=evaluated_candidate,
        risk_profile=risk_profile,
    )
    plan = risk_manager.evaluate(
        signal=scored_candidate.candidate.signal,
        snapshot=scored_candidate.candidate.snapshot,
        account_equity=100000.0,
        session_key=scored_candidate.candidate.session_key,
        effective_sl_tp=scored_candidate.effective_sl_tp,
    )

    assert scored_candidate.effective_sl_tp is evaluated_candidate.effective_sl_tp
    assert scored_candidate.effective_sl_tp is not None
    assert plan.approved
    assert plan.sl_tp_mode == scored_candidate.effective_sl_tp.mode
    assert plan.sl_tp_source == scored_candidate.effective_sl_tp.source
    assert plan.effective_stop_loss_percent == pytest.approx(
        scored_candidate.effective_sl_tp.stop_loss_percent,
    )
    assert plan.effective_take_profit_percent == pytest.approx(
        scored_candidate.effective_sl_tp.take_profit_percent,
    )
    assert evaluated_candidate.economics.effective_stop_loss_percent == pytest.approx(
        scored_candidate.effective_sl_tp.stop_loss_percent,
    )
    assert evaluated_candidate.economics.effective_take_profit_percent == pytest.approx(
        scored_candidate.effective_sl_tp.take_profit_percent,
    )
    assert scored_candidate.tp_feasibility is not None
    assert scored_candidate.tp_feasibility.effective_stop_loss_percent == pytest.approx(
        plan.effective_stop_loss_percent,
    )
    assert scored_candidate.tp_feasibility.effective_take_profit_percent == pytest.approx(
        plan.effective_take_profit_percent,
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
