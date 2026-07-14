from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from app.runtime.symbol_flow import _market_context_for_side


def test_market_context_uses_decision_snapshot_timestamp_not_candle_close():
    candle_close = datetime(2026, 7, 14, 10, 32, tzinfo=timezone.utc)
    snapshot_time = candle_close + timedelta(seconds=8)
    snapshot = Mock(timestamp=snapshot_time)
    service = Mock()
    service.build_candidate_context.return_value = 'context'

    result = _market_context_for_side(
        symbol='AAPL',
        side='BUY',
        snapshot=snapshot,
        market_context_service=service,
    )

    assert result == 'context'
    service.build_candidate_context.assert_called_once_with(
        symbol='AAPL',
        side='BUY',
        as_of=snapshot_time,
    )
