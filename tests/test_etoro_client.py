from app.brokers.etoro_client import EtoroClient
from app.config.settings import Settings

def test_find_instrument_id_uses_exact_symbol_match(monkeypatch):
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    def fake_get(path, params=None):
        return {
            'items': [
                {
                    'internalSymbolFull': 'BTCA',
                    'internalInstrumentDisplayName': 'Bitcoin / VAULTA',
                    'internalInstrumentId': 100134,
                },
                {
                    'internalSymbolFull': 'BTC',
                    'internalInstrumentDisplayName': 'Bitcoin',
                    'internalInstrumentId': 100000,
                },
            ]
        }

    monkeypatch.setattr(client, '_get', fake_get)

    instrument_id = client._find_instrument_id('BTC')

    assert instrument_id == 100000

def test_etoro_headers_include_required_keys():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    headers = client.headers

    assert headers['x-api-key'] == 'api-key'
    assert headers['x-user-key'] == 'user-key'
    assert 'x-request-id' in headers
    assert headers['Content-Type'] == 'application/json'


def test_to_market_snapshot_uses_mid_price_when_last_is_missing():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    snapshot = client._to_market_snapshot(
        symbol='BTC',
        rates_payload={
            'data': [
                {
                    'Bid': 100.0,
                    'Ask': 102.0,
                }
            ]
        },
    )

    assert snapshot.symbol == 'BTC'
    assert snapshot.bid == 100.0
    assert snapshot.ask == 102.0
    assert snapshot.last == 101.0