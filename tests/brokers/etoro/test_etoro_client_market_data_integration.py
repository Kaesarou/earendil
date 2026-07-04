from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.market_data_mapper import to_market_snapshots
from app.config.settings import Settings


def test_etoro_client_market_data_mapping_matches_extracted_mapper():
    rates_payload = {
        'rates': [
            {
                'instrumentID': 1001,
                'Bid': 199.5,
                'Ask': 200.5,
                'Last': 200.0,
            },
            {
                'instrumentId': 1002,
                'bidPrice': '349.0',
                'askPrice': '351.0',
            },
        ],
    }
    symbol_by_instrument_id = {
        1001: 'AAPL',
        1002: 'MSFT',
    }
    client = EtoroClient(
        settings=Settings(
            BROKER='etoro_demo',
            ETORO_API_KEY='api-key',
            ETORO_USER_KEY='user-key',
        ),
    )
    client.symbol_by_instrument_id = symbol_by_instrument_id

    client_snapshots = client._to_market_snapshots(rates_payload)
    mapper_snapshots = to_market_snapshots(
        rates_payload=rates_payload,
        symbol_by_instrument_id=symbol_by_instrument_id,
    )

    assert client_snapshots == mapper_snapshots
