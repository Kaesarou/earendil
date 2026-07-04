import pytest

from app.brokers.etoro.etoro_client import EtoroClient
from app.config.settings import Settings


def build_client() -> EtoroClient:
    return EtoroClient(
        settings=Settings(
            BROKER='etoro_demo',
            ETORO_API_KEY='api-key',
            ETORO_USER_KEY='user-key',
        ),
    )


def test_etoro_market_data_maps_multiple_rates_by_cached_instrument_id():
    client = build_client()
    client.symbol_by_instrument_id = {
        1001: 'AAPL',
        1002: 'MSFT',
    }

    snapshots = client._to_market_snapshots(
        {
            'rates': [
                {
                    'instrumentID': 1001,
                    'Bid': 199.5,
                    'Ask': 200.5,
                    'Last': 200.0,
                },
                {
                    'instrumentID': 1002,
                    'Bid': 349.0,
                    'Ask': 351.0,
                    'Last': 350.0,
                },
            ],
        },
    )

    assert set(snapshots) == {'AAPL', 'MSFT'}
    assert snapshots['AAPL'].symbol == 'AAPL'
    assert snapshots['AAPL'].bid == 199.5
    assert snapshots['AAPL'].ask == 200.5
    assert snapshots['AAPL'].last == 200.0
    assert snapshots['MSFT'].symbol == 'MSFT'
    assert snapshots['MSFT'].bid == 349.0
    assert snapshots['MSFT'].ask == 351.0
    assert snapshots['MSFT'].last == 350.0


def test_etoro_market_data_uses_mid_price_when_last_is_missing():
    client = build_client()
    client.symbol_by_instrument_id = {1001: 'AAPL'}

    snapshots = client._to_market_snapshots(
        {
            'rates': [
                {
                    'instrumentID': 1001,
                    'Bid': 199.0,
                    'Ask': 201.0,
                },
            ],
        },
    )

    assert snapshots['AAPL'].last == 200.0


def test_etoro_market_data_accepts_alternative_rate_key_names():
    client = build_client()
    client.symbol_by_instrument_id = {1001: 'AAPL'}

    snapshots = client._to_market_snapshots(
        {
            'rates': [
                {
                    'instrumentId': 1001,
                    'bidPrice': '199.5',
                    'askPrice': '200.5',
                    'lastPrice': '200.25',
                },
            ],
        },
    )

    assert snapshots['AAPL'].bid == 199.5
    assert snapshots['AAPL'].ask == 200.5
    assert snapshots['AAPL'].last == 200.25


def test_etoro_market_data_raises_when_instrument_symbol_is_not_cached():
    client = build_client()

    with pytest.raises(ValueError, match='Unable to find cached symbol'):
        client._to_market_snapshots(
            {
                'rates': [
                    {
                        'instrumentID': 9999,
                        'Bid': 199.0,
                        'Ask': 201.0,
                    },
                ],
            },
        )


def test_etoro_market_data_raises_when_required_bid_is_missing():
    client = build_client()
    client.symbol_by_instrument_id = {1001: 'AAPL'}

    with pytest.raises(ValueError, match='Unable to extract required float'):
        client._to_market_snapshots(
            {
                'rates': [
                    {
                        'instrumentID': 1001,
                        'Ask': 201.0,
                    },
                ],
            },
        )
