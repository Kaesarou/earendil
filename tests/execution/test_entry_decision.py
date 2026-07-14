from datetime import datetime, timezone
from types import SimpleNamespace

from app.execution.candidate_economics import CandidateEconomics, EvaluatedTradeCandidate
from app.execution.entry_decision import EntryAction, EntryDecisionEngine
from app.execution.trade_candidate import TradeCandidate
from app.instruments.models import AssetClass, EntryDecisionConfig
from app.market.market_context import (
    BenchmarkContext,
    BreadthContext,
    CandidateMarketContext,
    ContextAlignment,
    MarketDirection,
    MarketRegime,
    SectorContext,
)
from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal

NOW = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)


def market_context(alignment: ContextAlignment) -> CandidateMarketContext:
    regime = MarketRegime.RISK_ON if alignment != ContextAlignment.OPPOSED else MarketRegime.RISK_OFF
    return CandidateMarketContext(
        version='market_context_v1',
        as_of=NOW,
        asset_class=AssetClass.EQUITY_US,
        regime=regime,
        alignment=alignment,
        benchmark=BenchmarkContext('SPY', True, MarketDirection.BULLISH, 0.3, 0.1, 0.02, 0.0),
        breadth=BreadthContext(True, MarketDirection.BULLISH, 4, 4, 1.0, 3, 1, 0, 0.75, 0.2),
        sector=SectorContext('TECHNOLOGY', True, MarketDirection.BULLISH, 3, 3, 0.67, 0.2),
        symbol_session_return_percent=0.5,
        symbol_relative_strength_percent=0.2,
        reasons=('test',),
    )


def evaluated(
    *,
    last: float,
    alignment=ContextAlignment.ALIGNED,
    penalty=0.0,
    runway=100.0,
    remaining_move_quality='GOOD',
):
    snapshot = MarketSnapshot('TEST', last - 0.05, last + 0.05, last, NOW)
    candle = Candle('TEST', 60, 99.8, last, 99.7, last, None, NOW, NOW)
    signal = Signal(
        action='BUY',
        setup_quality=0.8,
        reason='test',
        metadata={'range_high': 100.0, 'snapshot_momentum_percent': 0.2},
    )
    candidate = TradeCandidate(
        symbol='TEST',
        snapshot=snapshot,
        candle=candle,
        signal=signal,
        score=120.0,
        rank_reason='test',
        entry_quality_metadata={'remaining_move_quality': remaining_move_quality},
        market_context=market_context(alignment),
    )
    feasibility = SimpleNamespace(
        raw_runway_score=runway,
        raw_tp_feasibility_penalty=penalty,
        tp_feasibility_hard_rejection_reason=None,
    )
    return EvaluatedTradeCandidate(
        candidate=candidate,
        economics=CandidateEconomics(
            position_value=100.0,
            expected_gross_profit=1.0,
            expected_net_profit=0.5,
            expected_net_profit_percent=0.5,
            estimated_total_cost=0.5,
            estimated_total_cost_percent=0.5,
            min_expected_net_profit_percent=0.1,
            required_min_expected_net_profit_amount=0.1,
        ),
        tp_feasibility=feasibility,
    )


def test_routes_to_selection_when_context_and_price_are_healthy():
    decision = EntryDecisionEngine().evaluate(
        evaluated_candidate=evaluated(last=100.05),
        config=EntryDecisionConfig(),
    )
    assert decision.action == EntryAction.READY_FOR_SELECTION
    assert decision.reason == 'entry_conditions_satisfied'


def test_waits_for_retest_when_price_is_moderately_extended():
    decision = EntryDecisionEngine().evaluate(
        evaluated_candidate=evaluated(last=100.20),
        config=EntryDecisionConfig(),
    )
    assert decision.action == EntryAction.WAIT_FOR_RETEST
    assert decision.retest_eligible is True


def test_skips_when_price_is_severely_extended():
    decision = EntryDecisionEngine().evaluate(
        evaluated_candidate=evaluated(last=100.50),
        config=EntryDecisionConfig(),
    )
    assert decision.action == EntryAction.SKIP
    assert decision.reason == 'price_too_extended_for_entry'


def test_skips_when_market_context_is_opposed():
    decision = EntryDecisionEngine().evaluate(
        evaluated_candidate=evaluated(last=100.05, alignment=ContextAlignment.OPPOSED),
        config=EntryDecisionConfig(),
    )
    assert decision.action == EntryAction.SKIP
    assert decision.reason == 'market_context_opposed'


def test_severe_penalty_without_a_useful_retest_is_skipped():
    decision = EntryDecisionEngine().evaluate(
        evaluated_candidate=evaluated(last=100.05, penalty=40.0, runway=10.0),
        config=EntryDecisionConfig(),
    )
    assert decision.action == EntryAction.SKIP
    assert decision.reason == 'severe_feasibility_penalty_without_useful_retest'


def test_severe_penalty_with_usable_structure_waits_for_retest():
    decision = EntryDecisionEngine().evaluate(
        evaluated_candidate=evaluated(last=100.20, penalty=40.0, runway=10.0),
        config=EntryDecisionConfig(),
    )
    assert decision.action == EntryAction.WAIT_FOR_RETEST
    assert decision.retest_eligible is True
    assert decision.diagnostics['structural_retest_score'] == 100.0
    assert decision.diagnostics['feasibility_runway_score'] == 10.0


def test_poor_structure_does_not_turn_severe_penalty_into_pending():
    decision = EntryDecisionEngine().evaluate(
        evaluated_candidate=evaluated(
            last=100.20,
            penalty=40.0,
            runway=100.0,
            remaining_move_quality='POOR',
        ),
        config=EntryDecisionConfig(),
    )
    assert decision.action == EntryAction.SKIP
    assert decision.reason == 'severe_feasibility_penalty_without_useful_retest'
    assert decision.diagnostics['structural_retest_score'] == 0.0
