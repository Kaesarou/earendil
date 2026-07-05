from datetime import datetime, timedelta, timezone

import pytest

from app.risk.stale_position_guard import StalePositionConfig, StalePositionGuard


def test_buy_stale_when_mfe_is_too_low():
    checked_at = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
    decision = StalePositionGuard().evaluate(
        side='BUY',
        entry_price=100.0,
        highest_price=100.4,
        lowest_price=99.8,
        opened_at=checked_at - timedelta(minutes=61),
        now=checked_at,
        estimated_total_cost_percent=0.3,
        config=StalePositionConfig(
            enabled=True,
            max_age_minutes=60,
            min_favorable_move_percent=0.5,
            buffer_percent=0.1,
        ),
    )

    assert decision.should_close
    assert decision.reason == 'stale_position_exit'
    assert decision.mfe_percent == pytest.approx(0.4)
    assert decision.required_mfe_percent == pytest.approx(0.5)
