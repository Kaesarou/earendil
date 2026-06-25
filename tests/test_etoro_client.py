import pytest

from app.brokers.etoro_client import EtoroClient
from app.config.settings import Settings

def test_etoro_open_position_is_blocked_when_ear_mode_is_not_real():
    settings = Settings(
        EAR_MODE='paper',
        REAL_TRADING_ENABLED=True,
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    with pytest.raises(RuntimeError, match='EAR_MODE=real'):
        client.open_position(
            symbol='BTC',
            side='BUY',
            amount=10.0,
            stop_loss=60000.0,
            take_profit=62000.0,
        )


def test_etoro_open_position_is_blocked_when_real_trading_flag_is_false():
    settings = Settings(
        EAR_MODE='real',
        REAL_TRADING_ENABLED=False,
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    with pytest.raises(RuntimeError, match='REAL_TRADING_ENABLED=true'):
        client.open_position(
            symbol='BTC',
            side='BUY',
            amount=10.0,
            stop_loss=60000.0,
            take_profit=62000.0,
        )


def test_etoro_close_position_is_blocked_when_real_trading_flag_is_false():
    settings = Settings(
        EAR_MODE='real',
        REAL_TRADING_ENABLED=False,
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    with pytest.raises(RuntimeError, match='REAL_TRADING_ENABLED=true'):
        client.close_position('position-id')

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

def test_etoro_open_order_path_uses_demo_endpoint_when_env_is_demo():
    settings = Settings(
        EAR_MODE='real',
        REAL_TRADING_ENABLED=True,
        ETORO_ENV='demo',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._open_order_path() == '/api/v2/trading/execution/demo/orders'


def test_etoro_open_order_path_uses_real_endpoint_when_env_is_real():
    settings = Settings(
        EAR_MODE='real',
        REAL_TRADING_ENABLED=True,
        ETORO_ENV='real',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._open_order_path() == '/api/v2/trading/execution/orders'


def test_etoro_open_position_sends_expected_demo_order_payload(monkeypatch):
    settings = Settings(
        EAR_MODE='real',
        REAL_TRADING_ENABLED=True,
        ETORO_ENV='demo',
        BASE_CURRENCY='USD',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)
    captured = {}

    monkeypatch.setattr(client, '_find_instrument_id', lambda symbol: 100000)

    def fake_post(path, payload):
        captured['path'] = path
        captured['payload'] = payload
        return {'positionId': 'demo-position-1'}

    monkeypatch.setattr(client, '_post', fake_post)

    position_id = client.open_position(
        symbol='BTC',
        side='BUY',
        amount=5.0,
        stop_loss=60000.0,
        take_profit=62000.0,
    )

    assert position_id == 'demo-position-1'
    assert captured['path'] == '/api/v2/trading/execution/demo/orders'
    assert captured['payload'] == {
        'action': 'open',
        'transaction': 'buy',
        'InstrumentID': 100000,
        'orderType': 'mkt',
        'leverage': 1,
        'amount': 5.0,
        'orderCurrency': 'usd',
    }
    assert client.position_instruments['demo-position-1'] == 100000


def test_etoro_close_position_sends_expected_payload(monkeypatch):
    settings = Settings(
        EAR_MODE='real',
        REAL_TRADING_ENABLED=True,
        ETORO_ENV='demo',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)
    client.position_instruments['demo-position-1'] = 100000
    captured = {}

    def fake_post(path, payload):
        captured['path'] = path
        captured['payload'] = payload
        return {'status': 'closed'}

    monkeypatch.setattr(client, '_post', fake_post)

    client.close_position('demo-position-1')

    assert captured['path'] == '/api/v1/trading/execution/market-close-orders/positions/demo-position-1'
    assert captured['payload'] == {
        'InstrumentId': 100000,
        'UnitsToDeduct': None,
    }
    assert 'demo-position-1' not in client.position_instruments

def test_etoro_close_position_path_uses_demo_endpoint_when_env_is_demo():
    settings = Settings(
        EAR_MODE='real',
        REAL_TRADING_ENABLED=True,
        ETORO_ENV='demo',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._close_position_path('123') == (
        '/api/v1/trading/execution/demo/market-close-orders/positions/123'
    )


def test_etoro_close_position_path_uses_real_endpoint_when_env_is_real():
    settings = Settings(
        EAR_MODE='real',
        REAL_TRADING_ENABLED=True,
        ETORO_ENV='real',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._close_position_path('123') == (
        '/api/v1/trading/execution/market-close-orders/positions/123'
    )