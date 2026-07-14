from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.execution.candidate_economics import CandidateEconomics, EvaluatedTradeCandidate
from app.execution.candidate_ranking import build_trade_candidate
from app.market.models import Candle, MarketSnapshot
from app.runtime.pending_entry import PendingEntryManager
from app.strategies.entry_confirmation import EntryConfirmationConfig
from app.strategies.signals import Signal

UTC = timezone.utc
NOW = datetime(2026, 7, 15, 14, 0, tzinfo=UTC)


def snapshot(*, bid=99.9, ask=100.1, last=100.0):
    return MarketSnapshot('AMD', bid, ask, last, NOW)


def candle():
    return Candle(
        'AMD',
        60,
        99.8,
        100.2,
        99.7,
        100.0,
        None,
        NOW - timedelta(minutes=1),
        NOW,
    )


def candidate():
    return build_trade_candidate(
        symbol='AMD',
        snapshot=snapshot(),
        candle=candle(),
        signal=Signal(
            action='BUY',
            setup_quality=0.8,
            reason='breakout',
            metadata={
                'range_high': 99.5,
                'close_position_percent': 90.0,
            },
        ),
        session_key='us-session',
        run_id='run-1',
    )


def evaluated(item):
    return EvaluatedTradeCandidate(
        candidate=item,
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
        tp_feasibility=SimpleNamespace(
            raw_runway_score=50.0,
            raw_tp_feasibility_penalty=25.0,
        ),
        readiness_reason='better_entry_required_at_structure',
    )


def test_pending_registration_has_stable_explicit_lineage():
    initial = candidate()
    manager = PendingEntryManager()
    first = manager.register(evaluated_candidate=evaluated(initial), max_candles=5)
    second = manager.register(evaluated_candidate=evaluated(initial), max_candles=5)

    registered = first[0].pending
    refreshed = second[0].pending
    assert registered.origin_candidate_id == initial.candidate_id
    assert registered.pending_entry_id
    assert refreshed.pending_entry_id == registered.pending_entry_id
    assert refreshed.origin_candidate_id == registered.origin_candidate_id


def test_reconstructed_candidate_keeps_origin_and_pending_ids_outside_signal_metadata():
    initial = candidate()
    manager = PendingEntryManager()
    pending = manager.register(
        evaluated_candidate=evaluated(initial),
        max_candles=5,
    )[0].pending
    confirmation_signal = Signal(
        action='BUY',
        setup_quality=0.8,
        reason='pending_confirmed',
        metadata={
            'range_high': 99.5,
            'close_position_percent': 90.0,
        },
    )
    rebuilt = build_trade_candidate(
        symbol='AMD',
        snapshot=snapshot(last=100.2),
        candle=candle(),
        signal=confirmation_signal,
        session_key='us-session',
        run_id='run-1',
        origin_candidate_id=pending.origin_candidate_id,
        pending_entry_id=pending.pending_entry_id,
    )

    assert rebuilt.candidate_id != initial.candidate_id
    assert rebuilt.origin_candidate_id == initial.candidate_id
    assert rebuilt.pending_entry_id == pending.pending_entry_id
    assert 'origin_candidate_id' not in rebuilt.signal.metadata
    assert 'pending_entry_id' not in rebuilt.signal.metadata


def test_spread_invalidation_carries_execution_observation():
    initial = candidate()
    manager = PendingEntryManager()
    pending = manager.register(
        evaluated_candidate=evaluated(initial),
        max_candles=5,
    )[0].pending

    observation = manager.observe(
        symbol='AMD',
        candle=candle(),
        snapshot=snapshot(bid=99.8, ask=100.2, last=100.0),
        signal=initial.signal,
        session_key='us-session',
        session_tradable=True,
        spread_percent=0.4,
        max_spread_percent=0.1,
        config=EntryConfirmationConfig(),
    )

    event = observation.events[0]
    assert event.event_type == 'pending_entry_invalidated'
    assert event.pending.pending_entry_id == pending.pending_entry_id
    assert event.reason == 'spread_too_high'
    assert event.diagnostics == {
        'spread_percent': 0.4,
        'maximum_allowed_spread_percent': 0.1,
        'bid': 99.8,
        'ask': 100.2,
        'last': 100.0,
        'observed_at': NOW,
        'observed_candles': 0,
    }
