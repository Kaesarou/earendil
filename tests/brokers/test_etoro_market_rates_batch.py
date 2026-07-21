from app.brokers.etoro.market_data_client import EtoroRestMarketDataClient


def test_get_market_rates_uses_raw_comma_separated_instrument_ids(
    tmp_path,
    monkeypatch,
):
    client = EtoroRestMarketDataClient(
        api_key='api-key',
        user_key='user-key',
        instrument_id_cache_path=str(tmp_path / 'ids.json'),
    )
    client.instrument_ids_by_symbol = {
        'BTC': 1004,
        'ETH': 1137,
        'AAPL': 1001,
    }
    client.symbol_by_instrument_id = {
        1004: 'BTC',
        1137: 'ETH',
        1001: 'AAPL',
    }
    captured = {}

    def fake_get(path, params=None):
        captured['path'] = path
        captured['params'] = params
        return {'rates': []}

    monkeypatch.setattr(client, '_get', fake_get)

    assert client.get_market_snapshots(['BTC', 'ETH', 'AAPL']) == {}
    assert captured['path'] == (
        '/api/v1/market-data/instruments/rates'
        '?instrumentIds=1004,1137,1001'
    )
    assert captured['params'] is None
    assert '%2C' not in captured['path']
