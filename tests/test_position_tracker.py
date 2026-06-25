from app.execution.position_tracker import PositionTracker
from app.market.models import MarketSnapshot
from app.risk.risk_manager import TradePlan


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


def test_position_tracker_returns_no_close_signal_inside_range():
    tracker = PositionTracker()
    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=buy_plan(),
        entry_price=100.0,
    )

    close_signals = tracker.evaluate_snapshot(
        MarketSnapshot.now('BTC', bid=99.0, ask=101.0, last=100.0)
    )

    assert close_signals == []


def test_position_tracker_closes_buy_when_stop_loss_is_hit():
    tracker = PositionTracker()
    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=buy_plan(),
        entry_price=100.0,
    )

    close_signals = tracker.evaluate_snapshot(
        MarketSnapshot.now('BTC', bid=94.0, ask=95.0, last=94.5)
    )

    assert len(close_signals) == 1
    assert close_signals[0].position_id == 'paper-1'
    assert close_signals[0].reason == 'stop_loss_hit'


def test_position_tracker_closes_buy_when_take_profit_is_hit():
    tracker = PositionTracker()
    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=buy_plan(),
        entry_price=100.0,
    )

    close_signals = tracker.evaluate_snapshot(
        MarketSnapshot.now('BTC', bid=110.0, ask=111.0, last=110.5)
    )

    assert len(close_signals) == 1
    assert close_signals[0].position_id == 'paper-1'
    assert close_signals[0].reason == 'take_profit_hit'


def test_position_tracker_ignores_other_symbols():
    tracker = PositionTracker()
    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=buy_plan(),
        entry_price=100.0,
    )

    close_signals = tracker.evaluate_snapshot(
        MarketSnapshot.now('ETH', bid=94.0, ask=95.0, last=94.5)
    )

    assert close_signals == []


def test_position_tracker_removes_closed_position():
    tracker = PositionTracker()
    tracker.record_open_position(
        position_id='paper-1',
        trade_plan=buy_plan(),
        entry_price=100.0,
    )

    closed_position = tracker.record_closed_position('paper-1')

    assert closed_position is not None
    assert closed_position.position_id == 'paper-1'
    assert not tracker.has_open_positions()