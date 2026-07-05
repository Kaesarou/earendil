from datetime import datetime, timezone

import pytest

from app.market.models import MarketSnapshot
from app.utils.commons import spread_percent


def snapshot(
    *,
    bid: float,
    ask: float,
    last: float,
) -> MarketSnapshot:
    return MarketSnapshot(
        symbol='AAPL',
        bid=bid,
        ask=ask,
        last=last,
        timestamp=datetime(2026, 7, 4, 18, 0, tzinfo=timezone.utc),
    )


def test_spread_percent_calculates_valid_spread():
    assert round(
        spread_percent(snapshot(bid=99.9, ask=100.1, last=100.0)),
        4,
    ) == 0.2


@pytest.mark.parametrize(
    ('bid', 'ask', 'last'),
    [
        (0.0, 100.1, 100.0),
        (99.9, 0.0, 100.0),
        (99.9, 100.1, 0.0),
        (100.1, 99.9, 100.0),
    ],
)
def test_spread_percent_returns_conservative_value_for_invalid_snapshot(
    bid: float,
    ask: float,
    last: float,
):
    assert spread_percent(snapshot(bid=bid, ask=ask, last=last)) == 100.0
