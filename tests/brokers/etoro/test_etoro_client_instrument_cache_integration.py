from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.instrument_cache import cached_instrument_id, remember_instrument_id


def build_uninitialized_client() -> EtoroClient:
    return object.__new__(EtoroClient)


def test_etoro_client_find_instrument_id_uses_same_cache_key_as_helper(monkeypatch):
    client = build_uninitialized_client()
    client.instrument_ids_by_symbol = {}
    client.symbol_by_instrument_id = {}

    remember_instrument_id(
        instrument_ids_by_symbol=client.instrument_ids_by_symbol,
        symbol_by_instrument_id=client.symbol_by_instrument_id,
        symbol='abc',
        instrument_id=100000,
    )

    def fail_if_called(path, params=None):
        raise AssertionError('instrument search endpoint should not be called when cache is populated')

    monkeypatch.setattr(client, '_get', fail_if_called)

    assert client._find_instrument_id('abc') == cached_instrument_id(
        instrument_ids_by_symbol=client.instrument_ids_by_symbol,
        symbol='abc',
    )


def test_etoro_client_find_instrument_id_populates_same_cache_shape_as_helper(monkeypatch):
    client = build_uninitialized_client()
    client.instrument_ids_by_symbol = {}
    client.symbol_by_instrument_id = {}

    def fake_get(path, params=None):
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

    assert client._find_instrument_id('abc') == 100000
    assert client.instrument_ids_by_symbol == {'ABC': 100000}
    assert client.symbol_by_instrument_id == {100000: 'ABC'}
