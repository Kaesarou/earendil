from datetime import datetime, timedelta, timezone

import pytest

from app.market_data_probe.metrics import StudyMetrics
from app.market_data_probe.models import NormalizedCandle, NormalizedRate


def rate(
    *,
    source: str,
    observed_at: datetime,
    source_timestamp: datetime,
    message_id: str | None,
    price_rate_id: str | None,
    last: float,
) -> NormalizedRate:
    return NormalizedRate(
        source=source,
        symbol='BTC',
        instrument_id=100000,
        bid=last - 1,
        ask=last + 1,
        last=last,
        price_source='broker_last',
        received_at=observed_at,
        source_timestamp=source_timestamp,
        message_id=message_id,
        price_rate_id=price_rate_id,
    )


def test_metrics_detect_quality_issues_and_request_reduction():
    metrics = StudyMetrics()
    minute = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)
    first = rate(
        source='websocket_rate',
        observed_at=minute + timedelta(seconds=2, milliseconds=100),
        source_timestamp=minute + timedelta(seconds=2),
        message_id='message-1',
        price_rate_id='rate-1',
        last=100.0,
    )
    duplicate_and_older = rate(
        source='websocket_rate',
        observed_at=minute + timedelta(seconds=3),
        source_timestamp=minute + timedelta(seconds=1),
        message_id='message-1',
        price_rate_id='rate-1',
        last=100.0,
    )
    metrics.add_rate(first)
    metrics.add_rate(duplicate_and_older)
    metrics.add_historical_candle(
        NormalizedCandle(
            source='rest_historical_candle',
            symbol='BTC',
            instrument_id=100000,
            interval='OneMinute',
            opened_at=minute,
            open=99.0,
            high=102.0,
            low=98.0,
            close=101.0,
            volume=0.0,
            potentially_incomplete=False,
        )
    )
    metrics.add_request('rest_rates', duration_ms=10.0, succeeded=True)
    metrics.add_request('rest_rates', duration_ms=12.0, succeeded=True)

    summary = metrics.summary(elapsed_seconds=60.0)
    ws = summary['rates']['websocket_rate']['BTC']

    assert ws['observations'] == 2
    assert ws['repeated_prices'] == 1
    assert ws['duplicate_message_ids'] == 1
    assert ws['duplicate_rate_ids'] == 1
    assert ws['out_of_order_source_timestamps'] == 1
    assert summary['request_budget']['reduction_percent'] == pytest.approx(
        83.333,
        abs=0.001,
    )
    comparison = summary['ohlc_comparison']['websocket_rate']['BTC']
    assert comparison['comparable_closed_minutes'] == 1
    assert comparison['mean_observations_per_minute'] == 2.0
