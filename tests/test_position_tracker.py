from datetime import datetime, timedelta, timezone

from app.execution.position_tracker import PositionCloseSignal, PositionTracker, TrackedPosition
from app.market.models import MarketSnapshot
from app.risk.models import TradePlan


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
    )


def sell_plan() -> TradePlan:
    return TradePlan(
        approved=True,
        reason='test_sell',
        symbol='BTC',
        side='SELL',
        amount=10.0,
        stop_loss=105.0,
        take_profit=90.0,
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
        timestamp=timestamp or datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc),
    )


def test_position_tracker_returns_no_close_signal_inside_range():
    tracker = PositionTracker()
    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=buy_plan(),
        entry_price=100.0,
    )

    close_signals = tracker.evaluate_snapshot(snapshot(last=100.0))

    assert close_signals == []


def test_tracked_position_defaults_do_not_enable_managed_stops():
    position = TrackedPosition(
        position_id='paper-1',
        symbol='BTC',
        side='BUY',
        amount=10.0,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        opened_at=datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc),
    )

    assert position.breakeven_stop_enabled is False
    assert position.breakeven_trigger_percent == 0.0
    assert position.breakeven_buffer_percent == 0.0
    assert position.trailing_stop_enabled is False
    assert position.trailing_stop_trigger_percent == 0.0
    assert position.trailing_stop_distance_percent == 0.0


def test_position_tracker_uses_trade_plan_managed_stop_settings_for_new_position():
    tracker = PositionTracker()

    tracked_position = tracker.record_open_position(
        position_id='paper-1',
        trade_plan=managed_buy_plan(),
        entry_price=100.0,
    )

    assert tracked_position.breakeven_stop_enabled is True
    assert tracked_position.breakeven_trigger_percent == 2.0
    assert tracked_position.breakeven_buffer_percent == 0.1
    assert tracked_position.trailing_stop_enabled is True
    assert tracked_position.trailing_stop_trigger_percent == 4.0
    assert tracked_position.trailing_stop_distance_percent == 1.0


def test_position_tracker_keeps_persisted_managed_stop_settings_on_restore():
    tracker = PositionTracker()
    persisted_position = TrackedPosition(
        position_id='paper-1',
        symbol='BTC',
        side='BUY',
        amount=10.0,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        opened_at=datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc),
        breakeven_stop_enabled=False,
        breakeven_trigger_percent=0.0,
        breakeven_buffer_percent=0.0,
        trailing_stop_enabled=False,
        trailing_stop_trigger_percent=0.0,
        trailing_stop_distance_percent=0.0,
    )

    tracker.restore_open_position(persisted_position)

    restored_position = tracker.open_positions_snapshot()[0]
    assert restored_position.initial_stop_loss == 95.0
    assert restored_position.highest_price == 100.0
    assert restored_position.lowest_price == 100.0
    assert restored_position.breakeven_stop_enabled is False
    assert restored_position.trailing_stop_enabled is False


def test_position_tracker_closes_buy_when_stop_loss_is_hit():
    tracker = PositionTracker()
    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=buy_plan(),
        entry_price=100.0,
    )

    close_signals = tracker.evaluate_snapshot(snapshot(last=94.5))

    assert len(close_signals) == 1
    assert close_signals[0].position_id == 'paper-1'
    assert close_signals[0].reason == 'stop_loss_hit'
    assert close_signals[0].exit_price == 94.5


def test_position_tracker_closes_buy_when_take_profit_is_hit():
    tracker = PositionTracker()
    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=buy_plan(),
        entry_price=100.0,
    )

    close_signals = tracker.evaluate_snapshot(snapshot(last=110.5))

    assert len(close_signals) == 1
    assert close_signals[0].position_id == 'paper-1'
    assert close_signals[0].reason == 'take_profit_hit'
    assert close_signals[0].exit_price == 110.5


def test_position_tracker_moves_buy_stop_to_break_even():
    tracker = PositionTracker()
    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=managed_buy_plan(),
        entry_price=100.0,
    )

    assert tracker.evaluate_snapshot(snapshot(last=102.5)) == []

    position = tracker.open_positions_snapshot()[0]
    assert position.stop_loss == 100.1

    close_signals = tracker.evaluate_snapshot(snapshot(last=100.05))

    assert len(close_signals) == 1
    assert close_signals[0].reason == 'break_even_stop_hit'


def test_position_tracker_trails_buy_stop_after_trigger():
    tracker = PositionTracker()
    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=managed_buy_plan(),
        entry_price=100.0,
    )

    assert tracker.evaluate_snapshot(snapshot(last=105.0)) == []

    position = tracker.open_positions_snapshot()[0]
    assert position.highest_price == 105.0
    assert position.stop_loss == 103.95

    close_signals = tracker.evaluate_snapshot(snapshot(last=103.90))

    assert len(close_signals) == 1
    assert close_signals[0].reason == 'trailing_stop_hit'


def test_position_tracker_ignores_other_symbols():
    tracker = PositionTracker()
    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=buy_plan(),
        entry_price=100.0,
    )

    close_signals = tracker.evaluate_snapshot(snapshot(symbol='ETH', last=94.5))

    assert close_signals == []


def test_position_tracker_removes_closed_position():
    tracker = PositionTracker()
    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=buy_plan(),
        entry_price=100.0,
    )

    close_signal = PositionCloseSignal(
        position_id='paper-1',
        symbol='BTC',
        side='BUY',
        exit_price=110.0,
        reason='take_profit_hit',
        detected_at=datetime(2026, 6, 25, 12, 5, tzinfo=timezone.utc),
    )

    closed_position = tracker.record_closed_position(close_signal)

    assert closed_position is not None
    assert closed_position.position_id == 'paper-1'
    assert not tracker.has_open_positions()


def test_position_tracker_calculates_positive_pnl_for_buy_take_profit():
    tracker = PositionTracker()
    opened_at = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)

    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=buy_plan(),
        entry_price=100.0,
        opened_at=opened_at,
    )

    close_signal = PositionCloseSignal(
        position_id='paper-1',
        symbol='BTC',
        side='BUY',
        exit_price=110.0,
        reason='take_profit_hit',
        detected_at=opened_at + timedelta(minutes=5),
    )

    closed_position = tracker.record_closed_position(close_signal)

    assert closed_position is not None
    assert closed_position.entry_price == 100.0
    assert closed_position.exit_price == 110.0
    assert closed_position.gross_pnl_percent == 10.0
    assert closed_position.gross_pnl == 1.0
    assert closed_position.duration_seconds == 300.0
    assert closed_position.close_reason == 'take_profit_hit'


def test_position_tracker_calculates_negative_pnl_for_buy_stop_loss():
    tracker = PositionTracker()
    opened_at = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)

    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=buy_plan(),
        entry_price=100.0,
        opened_at=opened_at,
    )

    close_signal = PositionCloseSignal(
        position_id='paper-1',
        symbol='BTC',
        side='BUY',
        exit_price=94.0,
        reason='stop_loss_hit',
        detected_at=opened_at + timedelta(minutes=2),
    )

    closed_position = tracker.record_closed_position(close_signal)

    assert closed_position is not None
    assert closed_position.gross_pnl_percent == -6.0
    assert closed_position.gross_pnl == -0.6
    assert closed_position.duration_seconds == 120.0
    assert closed_position.close_reason == 'stop_loss_hit'


def test_position_tracker_returns_none_when_closing_unknown_position():
    tracker = PositionTracker()

    close_signal = PositionCloseSignal(
        position_id='missing-position',
        symbol='BTC',
        side='BUY',
        exit_price=100.0,
        reason='stop_loss_hit',
        detected_at=datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc),
    )

    closed_position = tracker.record_closed_position(close_signal)

    assert closed_position is None
