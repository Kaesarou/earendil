from datetime import datetime, timezone

import pytest

from app.market_data_probe.historical_candles import (
    historical_candles_path,
    normalize_historical_candles,
)


def test_builds_documented_candle_path_and_validates_parameters():
    assert historical_candles_path(
        instrument_id=12,
        direction='desc',
        interval='OneMinute',
        candle_count=1000,
    ) == (
        '/api/v1/market-data/instruments/12/history/'
        'candles/desc/OneMinute/1000'
    )
    with pytest.raises(ValueError, match='direction'):
        historical_candles_path(
            instrument_id=12,
            direction='latest',
            interval='OneMinute',
            candle_count=10,
        )
    with pytest.raises(ValueError, match='between 1 and 1000'):
        historical_candles_path(
            instrument_id=12,
            direction='desc',
            interval='OneMinute',
            candle_count=1001,
        )


def test_normalizes_and_marks_current_minute_incomplete():
    payload = {
        'interval': 'OneMinute',
        'candles': [
            {
                'instrumentId': 12,
                'candles': [
                    {
                        'instrumentID': 12,
                        'fromDate': '2025-03-05T10:34:00Z',
                        'open': 1.70227,
                        'high': 1.70277,
                        'low': 1.70221,
                        'close': 1.70253,
                        'volume': 0,
                    },
                    {
                        'instrumentID': 12,
                        'fromDate': '2025-03-05T10:35:00Z',
                        'open': 1.70252,
                        'high': 1.70276,
                        'low': 1.70244,
                        'close': 1.70276,
                        'volume': 0,
                    },
                ],
            }
        ],
    }

    candles = normalize_historical_candles(
        payload,
        symbol='TEST',
        instrument_id=12,
        observed_at=datetime(
            2025,
            3,
            5,
            10,
            35,
            30,
            tzinfo=timezone.utc,
        ),
    )

    assert len(candles) == 2
    assert candles[0].potentially_incomplete is False
    assert candles[1].potentially_incomplete is True
    assert candles[0].volume == 0.0
