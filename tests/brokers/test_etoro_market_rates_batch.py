from app.brokers.etoro.etoro_client import EtoroClient
from app.config.settings import Settings


def test_get_market_rates_uses_raw_comma_separated_instrument_ids(monkeypatch):
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )
    client = EtoroClient(settings=settings)
    captured = {}

    def fake_get(path, params=None):
        captured['path'] = path
        captured['params'] = params
        return {'rates': []}

    monkeypatch.setattr(client, '_get', fake_get)

    client._get_market_rates([1004, 1137, 1001])

    assert captured['path'] == (
        '/api/v1/market-data/instruments/rates'
        '?instrumentIds=1004,1137,1001'
    )
    assert captured['params'] is None
    assert '%2C' not in captured['path']
