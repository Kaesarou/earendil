from datetime import datetime, timezone

from app.execution.position_tracker import PositionCloseSignal, PositionTracker
from app.risk.models import TradePlan


def test_closed_position_calculates_estimated_net_pnl_from_cost_percent():
    tracker = PositionTracker()
    opened_at = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    tracker.record_open_position(
        position_id='position-1',
        trade_plan=TradePlan(
            approved=True,
            reason='test',
            symbol='AAPL',
            side='BUY',
            amount=1_000.0,
            stop_loss=99.0,
            take_profit=102.0,
            estimated_total_cost_percent=0.15,
        ),
        entry_price=100.0,
        opened_at=opened_at,
    )

    closed = tracker.record_closed_position(
        PositionCloseSignal(
            position_id='position-1',
            symbol='AAPL',
            side='BUY',
            exit_price=101.0,
            reason='take_profit_hit',
            detected_at=opened_at,
        )
    )

    assert closed is not None
    assert closed.gross_pnl == 10.0
    assert closed.estimated_total_cost == 1.5
    assert closed.net_pnl_estimated == 8.5
    assert closed.net_pnl_percent_estimated == 0.85
