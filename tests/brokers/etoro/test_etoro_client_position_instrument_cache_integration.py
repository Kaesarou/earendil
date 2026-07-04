from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.position_instrument_cache import cached_position_instrument_id


def build_uninitialized_client() -> EtoroClient:
    return object.__new__(EtoroClient)


def test_etoro_client_remember_position_instrument_uses_same_cache_shape(monkeypatch):
    client = build_uninitialized_client()
    client.position_instruments = {}

    monkeypatch.setattr(client, '_find_instrument_id', lambda symbol: 100000)

    client.remember_position_instrument('position-1', 'ABC')

    assert client.position_instruments == {'position-1': 100000}
    assert cached_position_instrument_id(
        position_instruments=client.position_instruments,
        position_id='position-1',
    ) == 100000
