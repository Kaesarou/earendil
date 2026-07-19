from datetime import datetime, timedelta, timezone

from app.market_data_probe.models import (
    NormalizedCandle,
    optional_float,
    parse_broker_datetime,
)


def historical_candles_path(
    *,
    instrument_id: int,
    direction: str,
    interval: str,
    candle_count: int,
) -> str:
    if direction not in ('asc', 'desc'):
        raise ValueError(f'Unsupported candle direction: {direction}')
    if not 1 <= candle_count <= 1000:
        raise ValueError('candle_count must be between 1 and 1000')
    return (
        f'/api/v1/market-data/instruments/{instrument_id}/history/'
        f'candles/{direction}/{interval}/{candle_count}'
    )


def normalize_historical_candles(
    payload: dict,
    *,
    symbol: str,
    instrument_id: int,
    observed_at: datetime,
) -> list[NormalizedCandle]:
    interval = str(payload.get('interval') or 'unknown')
    result: list[NormalizedCandle] = []
    for group in payload.get('candles', []):
        if not isinstance(group, dict):
            continue
        group_instrument_id = group.get('instrumentId')
        if group_instrument_id is not None:
            try:
                if int(group_instrument_id) != instrument_id:
                    continue
            except (TypeError, ValueError):
                continue
        for raw_candle in group.get('candles', []):
            candle = _normalize_candle(
                raw_candle,
                source='rest_historical_candle',
                symbol=symbol,
                instrument_id=instrument_id,
                interval=interval,
                observed_at=observed_at,
            )
            if candle is not None:
                result.append(candle)
    return sorted(result, key=lambda candle: candle.opened_at)


def _normalize_candle(
    payload: object,
    *,
    source: str,
    symbol: str,
    instrument_id: int,
    interval: str,
    observed_at: datetime,
) -> NormalizedCandle | None:
    if not isinstance(payload, dict):
        return None
    opened_at = parse_broker_datetime(payload.get('fromDate'))
    open_price = optional_float(payload.get('open'))
    high = optional_float(payload.get('high'))
    low = optional_float(payload.get('low'))
    close = optional_float(payload.get('close'))
    if (
        opened_at is None
        or open_price is None
        or high is None
        or low is None
        or close is None
    ):
        return None
    close_time = opened_at + _interval_duration(interval)
    return NormalizedCandle(
        source=source,
        symbol=symbol,
        instrument_id=instrument_id,
        interval=interval,
        opened_at=opened_at,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=optional_float(payload.get('volume')),
        potentially_incomplete=observed_at.astimezone(timezone.utc) < close_time,
    )


def _interval_duration(interval: str) -> timedelta:
    durations = {
        'OneMinute': timedelta(minutes=1),
        'FiveMinutes': timedelta(minutes=5),
        'TenMinutes': timedelta(minutes=10),
        'FifteenMinutes': timedelta(minutes=15),
        'ThirtyMinutes': timedelta(minutes=30),
        'OneHour': timedelta(hours=1),
        'FourHours': timedelta(hours=4),
        'OneDay': timedelta(days=1),
        'OneWeek': timedelta(weeks=1),
    }
    return durations.get(interval, timedelta(minutes=1))
