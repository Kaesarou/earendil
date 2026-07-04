from app.brokers.etoro.endpoint_paths import instrument_rates_path, instrument_search_path
from app.brokers.etoro.etoro_client import EtoroClient


def build_uninitialized_client() -> EtoroClient:
    return object.__new__(EtoroClient)


def test_etoro_client_market_rates_path_matches_endpoint_helper(monkeypatch):
    captured = {}
    client = build_uninitialized_client()

    def fake_get(path: str, params=None):
        captured['path'] = path
        captured['params'] = params
        return {'rates': []}

    monkeypatch.setattr(client, '_get', fake_get)

    assert client._get_market_rates([1001, 1002, 1003]) == {'rates': []}
    assert captured == {
        'path': instrument_rates_path([1001, 1002, 1003]),
        'params': None,
    }


def test_etoro_client_instrument_search_path_matches_endpoint_helper(monkeypatch):
    captured = {}
    client = build_uninitialized_client()
    client.instrument_ids_by_symbol = {}
    client.symbol_by_instrument_id = {}

    def fake_get(path: str, params=None):
        captured['path'] = path
        captured['params'] = params
        return {
            'items': [
                {
                    'internalSymbolFull': 'ABC',
                    'internalInstrumentDisplayName': 'Instrument ABC',
                    'internalInstrumentId': 100000,
                },
            ],
        }

    monkeypatch.setattr(client, '_get', fake_get)

    assert client._find_instrument_id('ABC') == 100000
    assert captured == {
        'path': instrument_search_path(),
        'params': {'internalSymbolFull': 'ABC'},
    }
