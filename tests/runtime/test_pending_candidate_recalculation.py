from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

from app.execution.candidate_economics import CandidateEconomics, EvaluatedTradeCandidate
from app.execution.candidate_readiness import CandidateReadiness
from app.execution.candidate_selector import RejectedEvaluatedCandidateSelection
from app.execution.trade_candidate import TradeCandidate
from app.market.models import Candle, MarketSnapshot
from app.runtime.candidate_flow import route_candidate_readiness
from app.runtime.pending_candidate_lifecycle import reconcile_pending_selection_rejections
from app.runtime.pending_entry import PendingEntryManager, PendingEntryState
from app.strategies.entry_confirmation import EntryConfirmationConfig
from app.strategies.signals import Signal

NOW = datetime(2026, 7, 10, 15, 0, tzinfo=timezone.utc)


class FakeJournal:
    def __init__(self):
        self.events = []

    def write(self, event_type, payload):
        self.events.append((event_type, payload))


class FakeRiskManager:
    def risk_profile_for(self, symbol):
        return SimpleNamespace(entry_confirmation=EntryConfirmationConfig(max_candles=5))


def evaluated_candidate(
    *,
    readiness=CandidateReadiness.WAIT_CONFIRMATION,
    readiness_reason='insufficient_runway',
    expected_net_profit_percent=0.5,
    min_expected_net_profit_percent=0.1,
    pending_entry_id=None,
    origin_candidate_id='candidate-origin',
    hard_rejection_reason=None,
):
    signal = Signal(
        'BUY',
        0.8,
        'test',
        metadata={
            'range_high': 100.0,
            'range_low': 100.0,
            'snapshot_momentum_percent': 0.2,
            'atr_percent': 0.2,
        },
    )
    candle = Candle('AMD', 60, 100, 101, 99.5, 100.5, None, NOW, NOW)
    candidate = TradeCandidate(
        symbol='AMD',
        snapshot=MarketSnapshot('AMD', 100, 100.05, 100.5, NOW),
        candle=candle,
        signal=signal,
        score=120.0,
        rank_reason='test',
        session_key='US',
        candidate_id=(
            'candidate-rebuilt' if pending_entry_id else 'candidate-origin'
        ),
        origin_candidate_id=origin_candidate_id,
        pending_entry_id=pending_entry_id,
    )
    economics = CandidateEconomics(
        position_value=100.0,
        expected_gross_profit=1.0,
        expected_net_profit=0.5,
        expected_net_profit_percent=expected_net_profit_percent,
        estimated_total_cost=0.5,
        estimated_total_cost_percent=0.5,
        min_expected_net_profit_percent=min_expected_net_profit_percent,
        required_min_expected_net_profit_amount=0.1,
    )
    feasibility = SimpleNamespace(
        raw_runway_score=20.0,
        raw_tp_feasibility_penalty=39.98,
        tp_feasibility_hard_rejection_reason=hard_rejection_reason,
    )
    return EvaluatedTradeCandidate(
        candidate=candidate,
        economics=economics,
        tp_feasibility=feasibility,
        readiness=readiness,
        readiness_reason=readiness_reason,
    )


def confirmed_pending(manager):
    original = evaluated_candidate()
    manager.register(evaluated_candidate=original, max_candles=5, detected_at=NOW)
    pending = manager.snapshot()[0]
    manager._entries[pending.key] = replace(
        pending,
        state=PendingEntryState.CONFIRMED,
        observed_candles=2,
        confirmation_type='retest_continuation',
    )
    return pending


def test_wait_candidate_registers_pending_and_stays_out_of_tradable_set():
    manager = PendingEntryManager()
    journal = FakeJournal()
    tradable, rejected = route_candidate_readiness(
        evaluated_candidates=[evaluated_candidate()],
        risk_manager=FakeRiskManager(),
        pending_entry_manager=manager,
        trade_journal=journal,
    )
    assert tradable == []
    assert rejected[0].reason == 'insufficient_runway'
    pending = manager.snapshot()[0]
    assert pending.origin_candidate_id == 'candidate-origin'
    assert pending.pending_entry_id
    assert journal.events[0][1]['pending_entry_id'] == pending.pending_entry_id


def test_confirmed_candidate_recalculation_uses_top_level_pending_id():
    manager = PendingEntryManager()
    journal = FakeJournal()
    pending = confirmed_pending(manager)
    recalculated = evaluated_candidate(
        pending_entry_id=pending.pending_entry_id,
        origin_candidate_id=pending.origin_candidate_id,
    )

    tradable, rejected = route_candidate_readiness(
        evaluated_candidates=[recalculated],
        risk_manager=FakeRiskManager(),
        pending_entry_manager=manager,
        trade_journal=journal,
    )
    assert tradable == []
    assert rejected[0].reason == 'insufficient_runway'
    stored = manager.get(pending.key)
    assert stored.state == PendingEntryState.WAITING
    assert stored.observed_candles == 2


def test_confirmed_candidate_recalculated_reject_is_removed():
    manager = PendingEntryManager()
    journal = FakeJournal()
    pending = confirmed_pending(manager)
    recalculated = evaluated_candidate(
        readiness=CandidateReadiness.REJECT,
        readiness_reason='invalid_trade_structure',
        pending_entry_id=pending.pending_entry_id,
        origin_candidate_id=pending.origin_candidate_id,
    )
    tradable, rejected = route_candidate_readiness(
        evaluated_candidates=[recalculated],
        risk_manager=FakeRiskManager(),
        pending_entry_manager=manager,
        trade_journal=journal,
    )
    assert tradable == []
    assert rejected[0].reason == 'invalid_trade_structure'
    assert manager.get(pending.key) is None
    assert journal.events[-1][0] == 'pending_entry_invalidated'


def test_confirmed_tradable_candidate_reaches_selector_input():
    manager = PendingEntryManager()
    journal = FakeJournal()
    pending = confirmed_pending(manager)
    recalculated = evaluated_candidate(
        readiness=CandidateReadiness.TRADABLE_NOW,
        readiness_reason='tp_feasibility_ready',
        pending_entry_id=pending.pending_entry_id,
        origin_candidate_id=pending.origin_candidate_id,
    )
    tradable, rejected = route_candidate_readiness(
        evaluated_candidates=[recalculated],
        risk_manager=FakeRiskManager(),
        pending_entry_manager=manager,
        trade_journal=journal,
    )
    assert tradable == [recalculated]
    assert rejected == []
    assert manager.get(pending.key).state == PendingEntryState.CONFIRMED


def test_economically_invalid_confirmed_candidate_is_removed():
    manager = PendingEntryManager()
    journal = FakeJournal()
    pending = confirmed_pending(manager)
    recalculated = evaluated_candidate(
        readiness=CandidateReadiness.TRADABLE_NOW,
        pending_entry_id=pending.pending_entry_id,
        origin_candidate_id=pending.origin_candidate_id,
        expected_net_profit_percent=0.05,
        min_expected_net_profit_percent=0.10,
    )
    tradable, rejected = route_candidate_readiness(
        evaluated_candidates=[recalculated],
        risk_manager=FakeRiskManager(),
        pending_entry_manager=manager,
        trade_journal=journal,
    )
    assert tradable == []
    assert rejected[0].reason == 'candidate_selection_expected_profit_too_low_after_fees'
    assert manager.get(pending.key) is None


def test_pending_losing_top_n_returns_to_waiting_without_resetting_age():
    manager = PendingEntryManager()
    journal = FakeJournal()
    pending = confirmed_pending(manager)
    recalculated = evaluated_candidate(
        readiness=CandidateReadiness.TRADABLE_NOW,
        pending_entry_id=pending.pending_entry_id,
        origin_candidate_id=pending.origin_candidate_id,
    )
    reconcile_pending_selection_rejections(
        rejected_candidates=[
            RejectedEvaluatedCandidateSelection(
                evaluated_candidate=recalculated,
                reason='candidate_selection_outside_top_n',
            )
        ],
        pending_entry_manager=manager,
        trade_journal=journal,
    )
    stored = manager.get(pending.key)
    assert stored.state == PendingEntryState.WAITING
    assert stored.observed_candles == 2
    assert journal.events[-1][1]['reason'] == (
        'selection_retry:candidate_selection_outside_top_n'
    )
