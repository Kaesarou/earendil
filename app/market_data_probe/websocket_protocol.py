import json
from datetime import datetime
from uuid import uuid4

from app.market_data_probe.models import (
    NormalizedRate,
    optional_float,
    optional_string,
    parse_broker_datetime,
)


def build_authentication_request(
    *,
    api_key: str,
    user_key: str,
    request_id: str | None = None,
) -> dict:
    return {
        'id': request_id or str(uuid4()),
        'operation': 'Authenticate',
        'data': {'userKey': user_key, 'apiKey': api_key},
    }


def build_subscription_request(
    instrument_ids: list[int],
    *,
    snapshot: bool = True,
    request_id: str | None = None,
) -> dict:
    return {
        'id': request_id or str(uuid4()),
        'operation': 'Subscribe',
        'data': {
            'topics': [
                f'instrument:{instrument_id}'
                for instrument_id in instrument_ids
            ],
            'snapshot': snapshot,
        },
    }


def validate_authentication_response(
    raw_message: str,
    *,
    request_id: str,
) -> dict:
    payload = json.loads(raw_message)
    if not isinstance(payload, dict):
        raise ValueError('Unexpected WebSocket authentication response.')
    if payload.get('id') != request_id:
        raise ValueError('WebSocket authentication response id mismatch.')
    if payload.get('operation') != 'Authenticate':
        raise ValueError('Unexpected WebSocket authentication operation.')
    if payload.get('success') is not True:
        error_code = payload.get('errorCode') or 'unknown'
        error_message = payload.get('errorMessage') or 'unknown'
        raise RuntimeError(
            'eToro WebSocket authentication failed: '
            f'code={error_code}, message={error_message}'
        )
    return payload


def parse_websocket_rates(
    raw_message: str,
    *,
    symbol_by_instrument_id: dict[int, str],
    received_at: datetime,
    rate_state_by_instrument_id: dict[int, dict] | None = None,
) -> list[NormalizedRate]:
    payload = json.loads(raw_message)
    if not isinstance(payload, dict):
        return []
    messages = payload.get('messages')
    if not isinstance(messages, list):
        return []

    rates: list[NormalizedRate] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        topic = message.get('topic')
        if not isinstance(topic, str) or not topic.startswith('instrument:'):
            continue
        instrument_id = _instrument_id_from_topic(topic)
        if instrument_id is None:
            continue
        symbol = symbol_by_instrument_id.get(instrument_id)
        if symbol is None:
            continue
        content = _content_payload(message.get('content'))
        if not content:
            continue
        state_reconstructed = False
        if rate_state_by_instrument_id is not None:
            is_snapshot = message.get('type') == 'Snapshot'
            previous = (
                {}
                if is_snapshot
                else rate_state_by_instrument_id.get(instrument_id, {})
            )
            content = {**previous, **content}
            rate_state_by_instrument_id[instrument_id] = content
            state_reconstructed = bool(previous)
        rate = normalize_rate_payload(
            content,
            source='websocket_rate',
            symbol=symbol,
            instrument_id=instrument_id,
            received_at=received_at,
            message_id=optional_string(message.get('id')),
            state_reconstructed=state_reconstructed,
        )
        if rate is not None:
            rates.append(rate)
    return rates


def normalize_rate_payload(
    payload: dict,
    *,
    source: str,
    symbol: str,
    instrument_id: int,
    received_at: datetime,
    message_id: str | None = None,
    state_reconstructed: bool = False,
) -> NormalizedRate | None:
    bid = _first_float(payload, 'Bid', 'bid', 'bidPrice')
    ask = _first_float(payload, 'Ask', 'ask', 'askPrice')
    if bid is None or ask is None:
        return None
    last = _first_float(
        payload,
        'LastExecution',
        'lastExecution',
        'Last',
        'last',
        'lastPrice',
        'Price',
        'price',
    )
    price_source = 'broker_last'
    if last is None:
        last = (bid + ask) / 2
        price_source = 'bid_ask_midpoint'
    source_timestamp = _first_datetime(
        payload,
        'Date',
        'date',
        'lastUpdate',
        'LastUpdate',
    )
    price_rate_id = _first_string(
        payload,
        'PriceRateID',
        'priceRateID',
        'priceRateId',
    )
    return NormalizedRate(
        source=source,
        symbol=symbol,
        instrument_id=instrument_id,
        bid=bid,
        ask=ask,
        last=last,
        price_source=price_source,
        received_at=received_at,
        source_timestamp=source_timestamp,
        message_id=message_id,
        price_rate_id=price_rate_id,
        state_reconstructed=state_reconstructed,
    )


def _content_payload(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _instrument_id_from_topic(topic: str) -> int | None:
    try:
        return int(topic.split(':', 1)[1])
    except (IndexError, ValueError):
        return None


def _first_float(payload: dict, *keys: str) -> float | None:
    for key in keys:
        value = optional_float(payload.get(key))
        if value is not None:
            return value
    return None


def _first_string(payload: dict, *keys: str) -> str | None:
    for key in keys:
        value = optional_string(payload.get(key))
        if value is not None:
            return value
    return None


def _first_datetime(payload: dict, *keys: str) -> datetime | None:
    for key in keys:
        value = parse_broker_datetime(payload.get(key))
        if value is not None:
            return value
    return None
