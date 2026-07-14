from datetime import datetime, timezone

from app.market.models import Candle
from app.strategies.entry_confirmation import EntryConfirmationConfig, EntryConfirmationEvaluator
from app.strategies.signals import Signal

NOW = datetime(2026, 7, 10, 15, 0, tzinfo=timezone.utc)
CONFIG = EntryConfirmationConfig(consecutive_closes=2)


def candle(open_, high, low, close):
    return Candle('X', 60, open_, high, low, close, None, NOW, NOW)


def signal(side, momentum):
    return Signal(action=side, setup_quality=0.8, reason='test', metadata={'snapshot_momentum_percent': momentum, 'atr_percent': 0.2})


def evaluate(side, current_candle, current_signal, state='waiting', closes=0, retest=None, structure=None):
    return EntryConfirmationEvaluator().evaluate(
        side=side,
        breakout_level=100.0,
        previous_state=state,
        previous_consecutive_closes=closes,
        previous_retest_extreme_price=retest,
        previous_structure_extreme_price=structure,
        candle=current_candle,
        signal=current_signal,
        spread_percent=0.05,
        config=CONFIG,
    )


def test_buy_retest_then_continuation_confirms():
    first = evaluate('BUY', candle(100.3, 100.5, 99.95, 100.1), signal('BUY', 0.2))
    second = evaluate('BUY', candle(100.05, 100.8, 100.0, 100.7), signal('BUY', 0.3), state=first.state, retest=first.retest_extreme_price, structure=first.structural_invalidation_price)
    assert first.state == 'retest_detected'
    assert second.state == 'confirmed'
    assert second.confirmation_type == 'retest_continuation'
    assert second.structural_invalidation_price == 99.95


def test_sell_retest_then_continuation_confirms():
    first = evaluate('SELL', candle(99.7, 100.05, 99.5, 99.9), signal('SELL', -0.2))
    second = evaluate('SELL', candle(99.95, 100.0, 99.1, 99.2), signal('SELL', -0.3), state=first.state, retest=first.retest_extreme_price, structure=first.structural_invalidation_price)
    assert second.state == 'confirmed'
    assert second.structural_invalidation_price == 100.05


def test_persistent_closes_without_retest_do_not_confirm():
    first = evaluate('BUY', candle(100.4, 100.8, 100.3, 100.6), signal('BUY', 0.2))
    second = evaluate('BUY', candle(100.6, 101.0, 100.4, 100.8), signal('BUY', 0.2), state=first.state, closes=first.consecutive_closes, structure=first.structural_invalidation_price)

    assert first.state == 'waiting'
    assert second.state == 'waiting'
    assert second.confirmation_type is None
    assert second.reason == 'waiting_for_retest'


def test_momentum_inversion_invalidates():
    decision = evaluate('BUY', candle(100.0, 100.5, 99.9, 100.2), signal('HOLD', -0.1))
    assert decision.state == 'invalidated'
    assert decision.reason == 'momentum_inverted'


def test_structure_break_invalidates():
    decision = evaluate('BUY', candle(100.0, 100.1, 99.0, 99.2), signal('HOLD', 0.1))
    assert decision.state == 'invalidated'
    assert decision.reason == 'structure_invalidated'
