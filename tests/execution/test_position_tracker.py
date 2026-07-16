from datetime import datetime, timedelta, timezone

from app.execution.position_tracker import (
    PositionCloseSignal,
    PositionTracker,
    TrackedPosition,
)
from app.market.models import MarketSnapshot
from app.risk.models import TradePlan


OPENED_AT = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)


def buy_plan() -> TradePlan:
    return TradePlan(
        approved=True,
        reason='test_buy',
        symbol='BTC',
        side='BUY',
        amount=10.0,
        stop_loss=95.0,
        take_profit=110.0,
    )


def managed_buy_plan() -> TradePlan:
    return TradePlan(
        approved=True,
        reason='test_buy',
        symbol='BTC',
        side='BUY',
        amount=10.0,
        stop_loss=95.0,
        take_profit=120.0,
        breakeven_stop_enabled=True,
        breakeven_trigger_percent=2.0,
        breakeven_buffer_percent=0.1,
        trailing_stop_enabled=True,
        trailing_stop_trigger_percent=4.0,
        trailing_stop_distance_percent=1.0,
        trailing_stop_net_buffer_percent=0.1,
        estimated_total_cost_percent=0.0,
    )


def net_aware_buy_plan() -> TradePlan:
    return TradePlan(
        approved=True,
        reason='test_buy',
        symbol='BTC',
        side='BUY',
        amount=10.0,
        stop_loss=98.0,
        take_profit=103.0,
        breakeven_stop_enabled=True,
        breakeven_trigger_percent=0.9,
        breakeven_buffer_percent=0.05,
        trailing_stop_enabled=True,
        trailing_stop_trigger_percent=1.0,
        trailing_stop_distance_percent=0.8,
        trailing_stop_net_buffer_percent=0.1,
        estimated_total_cost_percent=0.35,
    )


def net_aware_sell_plan() -> TradePlan:
    return TradePlan(
        approved=True,
        reason='test_sell',
        symbol='BTC',
        side='SELL',
        amount=10.0,
        stop_loss=102.0,
        take_profit=97.0,
        breakeven_stop_enabled=True,
        breakeven_trigger_percent=0.9,
        breakeven_buffer_percent=0.05,
        trailing_stop_enabled=True,
        trailing_stop_trigger_percent=1.0,
        trailing_stop_distance_percent=0.8,
        trailing_stop_net_buffer_percent=0.1,
        estimated_total_cost_percent=0.35,
    )


def snapshot(
    symbol: str = 'BTC',
    last: float = 100.0,
    timestamp: datetime | None = None,
) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        bid=last - 0.5,
        ask=last + 0.5,
        last=last,
        timestamp=timestamp or OPENED_AT,
    )


def test_position_tracker_keeps_positions_inside_range_and_ignores_other_symbols():
    tracker = PositionTracker()
    tracker.record_open_position('paper-1', buy_plan(), 100.0)
    assert tracker.evaluate_snapshot(snapshot(last=100.0)) == []
    assert tracker.evaluate_snapshot(snapshot(symbol='ETH', last=94.5)) == []


def test_position_tracker_closes_buy_at_stop_or_take_profit():
    stop_tracker = PositionTracker()
    stop_tracker.record_open_position('stop', buy_plan(), 100.0)
    stop = stop_tracker.evaluate_snapshot(snapshot(last=94.5))[0]
    assert stop.reason == 'stop_loss_hit'

    tp_tracker = PositionTracker()
    tp_tracker.record_open_position('tp', buy_plan(), 100.0)
    take_profit = tp_tracker.evaluate_snapshot(snapshot(last=110.5))[0]
    assert take_profit.reason == 'take_profit_hit'


def test_position_tracker_moves_buy_stop_to_net_breakeven_and_exposes_update():
    tracker = PositionTracker()
    tracker.record_open_position('paper-1', managed_buy_plan(), 100.0)
    assert tracker.evaluate_snapshot(snapshot(last=102.5)) == []
    position = tracker.open_positions_snapshot()[0]
    assert position.stop_loss == 100.1
    assert position.managed_stop_protection_type == 'net_breakeven'
    updates = tracker.consume_managed_stop_updates()
    assert len(updates) == 1
    assert updates[0].previous_position.stop_loss == 95.0
    assert updates[0].position.stop_loss == 100.1
    assert tracker.consume_managed_stop_updates() == ()

    close = tracker.evaluate_snapshot(snapshot(last=100.05))[0]
    assert close.reason == 'net_breakeven_stop_hit'
    assert close.metadata['managed_stop_protection_type'] == 'net_breakeven'


def test_position_tracker_trails_buy_and_sell_stops_after_net_trigger():
    buy_tracker = PositionTracker()
    buy_tracker.record_open_position('buy', managed_buy_plan(), 100.0)
    assert buy_tracker.evaluate_snapshot(snapshot(last=105.0)) == []
    buy = buy_tracker.open_positions_snapshot()[0]
    assert buy.stop_loss == 103.95
    assert buy.managed_stop_protection_type == 'trailing'
    assert buy_tracker.evaluate_snapshot(snapshot(last=103.90))[0].reason == 'trailing_stop_hit'

    sell_tracker = PositionTracker()
    sell_tracker.record_open_position('sell', net_aware_sell_plan(), 100.0)
    assert sell_tracker.evaluate_snapshot(snapshot(last=98.0)) == []
    sell = sell_tracker.open_positions_snapshot()[0]
    assert sell.stop_loss == 98.784
    assert sell.managed_stop_protection_type == 'trailing'
    assert sell_tracker.evaluate_snapshot(snapshot(last=98.9))[0].reason == 'trailing_stop_hit'


def test_non_protective_trailing_keeps_net_breakeven():
    tracker = PositionTracker()
    tracker.record_open_position('paper-1', net_aware_buy_plan(), 100.0)
    assert tracker.evaluate_snapshot(snapshot(last=101.0)) == []
    position = tracker.open_positions_snapshot()[0]
    assert position.stop_loss == 100.4
    assert position.managed_stop_protection_type == 'net_breakeven'


def test_restore_preserves_managed_stop_state():
    tracker = PositionTracker()
    persisted = TrackedPosition(
        position_id='paper-1',
        symbol='BTC',
        side='BUY',
        amount=10.0,
        entry_price=100.0,
        stop_loss=100.4,
        take_profit=110.0,
        opened_at=OPENED_AT,
        trailing_stop_net_buffer_percent=0.2,
        managed_stop_protection_type='net_breakeven',
    )
    tracker.restore_open_position(persisted)
    restored = tracker.open_positions_snapshot()[0]
    assert restored.initial_stop_loss == 100.4
    assert restored.highest_price == 100.0
    assert restored.lowest_price == 100.0
    assert restored.managed_stop_protection_type == 'net_breakeven'


def test_closed_position_pnl_and_unknown_close_behavior():
    tracker = PositionTracker()
    tracker.record_open_position('paper-1', buy_plan(), 100.0, opened_at=OPENED_AT)
    signal = PositionCloseSignal(
        position_id='paper-1',
        symbol='BTC',
        side='BUY',
        exit_price=110.0,
        reason='take_profit_hit',
        detected_at=OPENED_AT + timedelta(minutes=5),
    )
    closed = tracker.record_closed_position(signal)
    assert closed.gross_pnl_percent == 10.0
    assert closed.gross_pnl == 1.0
    assert closed.duration_seconds == 300.0
    assert not tracker.has_open_positions()

    missing = PositionCloseSignal(
        position_id='missing',
        symbol='BTC',
        side='BUY',
        exit_price=100.0,
        reason='stop_loss_hit',
        detected_at=OPENED_AT,
    )
    assert tracker.record_closed_position(missing) is None
