from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.instrument_search_parser import resolve_exact_instrument_id
from app.config.settings import Settings


def build_client() -> EtoroClient:
    return EtoroClient(
        settings=Settings(
            BROKER='etoro_demo',
            ETORO_API_KEY='api-key',
            ETORO_USER_KEY='user-key',
        )
    )


def test_etoro_client_find_instrument_id_matches_parser(monkeypatch):
    payload = {
        'items': [
            {
                'internalSymbolFull': 'ABCD',
                'internalInstrumentDisplayName': 'Instrument ABCD',
                'internalInstrumentId': 100134,
            },
            {
                'internalSymbolFull': 'ABC',
                'internalInstrumentDisplayName': 'Instrument ABC',
                'internalInstrumentId': 100000,
            },
        ]
    }
    client = build_client()

    monkeypatch.setattr(client, '_get', lambda path, params=None: payload)

    assert client._find_instrument_id('ABC') == resolve_exact_instrument_id('ABC', payload)
    assert client.instrument_ids_by_symbol['ABC'] == 100000
    assert client.symbol_by_instrument_id[100000] == 'ABC'


def test_etoro_client_find_instrument_id_uses_cache_before_parser(monkeypatch):
    client = build_client()
    client.instrument_ids_by_symbol['ABC'] = 100000

    def fail_if_called(path, params=None):
        raise AssertionError('instrument search endpoint should not be called when cache is populated')

    monkeypatch.setattr(client, '_get', fail_if_called)

    assert client._find_instrument_id('ABC') == 100000
