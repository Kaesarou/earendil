import json
from datetime import datetime, timezone

import pytest

from app.market_data_probe.websocket_protocol import (
    build_authentication_request,
    build_subscription_request,
    parse_websocket_rates,
    validate_authentication_response,
)


def test_builds_documented_authentication_and_subscription_requests():
    auth = build_authentication_request(
        api_key='api-key',
        user_key='user-key',
        request_id='auth-1',
    )
    subscription = build_subscription_request(
        [100000, 100001],
        request_id='sub-1',
    )

    assert auth == {
        'id': 'auth-1',
        'operation': 'Authenticate',
        'data': {'userKey': 'user-key', 'apiKey': 'api-key'},
    }
    assert subscription == {
        'id': 'sub-1',
        'operation': 'Subscribe',
        'data': {
            'topics': ['instrument:100000', 'instrument:100001'],
            'snapshot': True,
        },
    }


def test_validates_authentication_response_without_accepting_failure():
    success = json.dumps(
        {'id': 'auth-1', 'success': True, 'operation': 'Authenticate'}
    )
    failure = json.dumps(
        {
            'id': 'auth-1',
            'success': False,
            'operation': 'Authenticate',
            'errorCode': 'InvalidKey',
        }
    )

    assert validate_authentication_response(
        success,
        request_id='auth-1',
    )['success'] is True
    with pytest.raises(RuntimeError, match='InvalidKey'):
        validate_authentication_response(failure, request_id='auth-1')


def test_parses_documented_instrument_rate_message():
    raw_message = json.dumps(
        {
            'messages': [
                {
                    'topic': 'instrument:100000',
                    'content': json.dumps(
                        {
                            'Ask': '84917.73',
                            'Bid': '83232.21',
                            'LastExecution': '84072.94',
                            'Date': '2025-04-01T08:36:02.8305456Z',
                            'PriceRateID': '106439224591',
                        }
                    ),
                    'id': 'message-1',
                    'type': 'Trading.Instrument.Rate',
                }
            ]
        }
    )
    received_at = datetime(2025, 4, 1, 8, 36, 3, tzinfo=timezone.utc)

    rates = parse_websocket_rates(
        raw_message,
        symbol_by_instrument_id={100000: 'BTC'},
        received_at=received_at,
    )

    assert len(rates) == 1
    rate = rates[0]
    assert rate.symbol == 'BTC'
    assert rate.bid == 83232.21
    assert rate.ask == 84917.73
    assert rate.last == 84072.94
    assert rate.source_timestamp == datetime(
        2025,
        4,
        1,
        8,
        36,
        2,
        830545,
        tzinfo=timezone.utc,
    )
    assert rate.message_id == 'message-1'
    assert rate.price_rate_id == '106439224591'


def test_ignores_unknown_topics_and_invalid_content():
    raw_message = json.dumps(
        {
            'messages': [
                {'topic': 'private', 'content': '{}'},
                {'topic': 'instrument:abc', 'content': '{}'},
                {'topic': 'instrument:100000', 'content': 'not-json'},
            ]
        }
    )

    assert parse_websocket_rates(
        raw_message,
        symbol_by_instrument_id={100000: 'BTC'},
        received_at=datetime.now(timezone.utc),
    ) == []
