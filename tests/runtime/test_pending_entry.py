from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.execution.candidate_economics import CandidateEconomics, EvaluatedTradeCandidate
from app.execution.trade_candidate import TradeCandidate
from app.market.models import Candle, MarketSnapshot
from app.runtime.pending_entry import PendingEntryManager
from app.strategies.entry_confirmation import EntryConfirmationConfig
from app.strategies.signals import Signal

NOW = datetime(2026, 7, 10, 15, 0, tzinfo=timezone.utc)


def candle(close=100.2, low=99.9, high=100.5, open_=100.0, minute=0):
    timestamp = NOW + timedelta(minutes=minute)
    return Candle(
        'AMD',
        60,
        open_,
        high,
        low,
        close,
        None,
        timestamp - timedelta(minutes=1),
        timestamp,
    )


def evaluated(side='BUY', score=120.0):
    signal = Signal(
        action=side,
        confidence=0.8,
        reason='test',
        metadata={
            'range_high': 100.0,
            'range_low': 100.0,
            'snapshot_momentum_percent': 0.2 if side == 'BUY' else -0.2,
            'atr_percent': 0.2,
        },
    )
    current_candle = candle()
    candidate = TradeCandidate(
        'AMD',
        MarketSnapshot('AMD', 100, 100.05, 100.2, NOW),
        current_candle,
        signal,
        score,
        'test',
        'US',
    )
    economics = CandidateEconomics(100, 1, 0.5, 0.5, 0.5, 0.5, 0.1, 0.1)
    analysis = SimpleNamespace(
        raw_runway_score=20.0,
        raw_tp_feasibility_penalty=39.98,
    )
    return EvaluatedTradeCandidate(
        candidate,
        economics,
        tp_feasibility=analysis,
        readiness_reason='insufficient_runway',
    )


def test_register_and_deduplicate_without_extending_expiry():
    manager = PendingEntryManager()
    first = manager.register(
        evaluated_candidate=evaluated(),
        max_candles=5,
        detected_at=NOW,
    )
    original = manager.snapshot()[0]
    second = manager.register(
        evaluated_candidate=evaluated(score=130),
        max_candles=5,
        detected_at=NOW + timedelta(minutes=10),
    )
    updated = manager.snapshot()[0]

    assert first[0].event_type == 'pending_entry_registered'
    assert second[0].event_type == 'pending_entry_updated'
    assert updated.detected_at == original.detected_at
    assert updated.expires_after_candles == 5


def test_opposite_signal_invalidates_existing_pending():
    manager = PendingEntryManager()
    manager.register(evaluated_candidate=evaluated('BUY'), max_candles=5)

    events = manager.register(
        evaluated_candidate=evaluated('SELL'),
        max_candles=5,
    )

    assert events[0].reason == 'opposite_signal'
    assert manager.snapshot()[0].side == 'SELL'


def test_pending_expires_after_max_candles():
    manager = PendingEntryManager()
    manager.register(evaluated_candidate=evaluated(), max_candles=1)

    result = manager.observe(
        symbol='AMD',
        candle=candle(close=100.0),
        snapshot=evaluated().candidate.snapshot,
        signal=Signal.hold('wait'),
        session_key='US',
        session_tradable=True,
        spread_percent=0.05,
        config=EntryConfirmationConfig(max_candles=1),
    )

    assert result.events[-1].event_type == 'pending_entry_expired'
    assert manager.snapshot() == []


def test_cooldown_invalidates_pending():
    manager = PendingEntryManager()
    manager.register(evaluated_candidate=evaluated(), max_candles=5)

    result = manager.observe(
        symbol='AMD',
        candle=candle(),
        snapshot=evaluated().candidate.snapshot,
        signal=Signal.hold('wait'),
        session_key='US',
        session_tradable=True,
        spread_percent=0.05,
        config=EntryConfirmationConfig(),
        cooldown_active=True,
    )

    assert result.events[0].reason == 'cooldown_registered'
    assert manager.snapshot() == []


def test_spread_too_high_invalidates_pending():
    manager = PendingEntryManager()
    manager.register(evaluated_candidate=evaluated(), max_candles=5)

    result = manager.observe(
        symbol='AMD',
        candle=candle(),
        snapshot=evaluated().candidate.snapshot,
        signal=Signal.hold('wait'),
        session_key='US',
        session_tradable=True,
        spread_percent=0.25,
        max_spread_percent=0.10,
        config=EntryConfirmationConfig(),
    )

    assert result.events[0].reason == 'spread_too_high'
    assert manager.snapshot() == []


def test_invalid_market_data_invalidates_pending():
    manager = PendingEntryManager()
    manager.register(evaluated_candidate=evaluated(), max_candles=5)
    invalid_snapshot = MarketSnapshot('AMD', 0.0, 100.05, 100.2, NOW)

    result = manager.observe(
        symbol='AMD',
        candle=candle(),
        snapshot=invalid_snapshot,
        signal=Signal.hold('wait'),
        session_key='US',
        session_tradable=True,
        spread_percent=0.05,
        config=EntryConfirmationConfig(),
    )

    assert result.events[0].reason == 'invalid_market_data'
    assert manager.snapshot() == []


def test_session_end_invalidates_pending():
    manager = PendingEntryManager()
    manager.register(evaluated_candidate=evaluated(), max_candles=5)

    events = manager.invalidate_session('US')

    assert events[0].event_type == 'pending_entry_invalidated'
    assert manager.snapshot() == []
