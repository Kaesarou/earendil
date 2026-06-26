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
    assert headers['Accept'] == 'application/json'


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


def test_etoro_demo_order_details_path():
    settings = Settings(
        ETORO_ENV='demo',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._demo_order_details_path('123') == (
        '/api/v1/trading/info/demo/orders/123'
    )


def test_etoro_real_order_lookup_path():
    settings = Settings(
        ETORO_ENV='real',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._real_order_lookup_path() == '/api/v2/trading/info/orders:lookup'


def test_etoro_demo_portfolio_path():
    settings = Settings(
        ETORO_ENV='demo',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._demo_portfolio_path() == '/api/v1/trading/info/demo/portfolio'


def test_etoro_real_portfolio_path():
    settings = Settings(
        ETORO_ENV='real',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._real_portfolio_path() == '/api/v1/trading/info/portfolio'


def test_get_order_details_uses_demo_order_details_endpoint(monkeypatch):
    settings = Settings(
        ETORO_ENV='demo',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)
    captured = {}

    def fake_get(path, params=None):
        captured['path'] = path
        captured['params'] = params
        return {'orderId': 123}

    monkeypatch.setattr(client, '_get', fake_get)

    result = client.get_order_details('123')

    assert result == {'orderId': 123}
    assert captured['path'] == '/api/v1/trading/info/demo/orders/123'
    assert captured['params'] is None


def test_get_order_details_uses_real_order_lookup_endpoint(monkeypatch):
    settings = Settings(
        ETORO_ENV='real',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)
    captured = {}

    def fake_get(path, params=None):
        captured['path'] = path
        captured['params'] = params
        return {'orderId': 123}

    monkeypatch.setattr(client, '_get', fake_get)

    result = client.get_order_details('123')

    assert result == {'orderId': 123}
    assert captured['path'] == '/api/v2/trading/info/orders:lookup'
    assert captured['params'] == {'orderId': '123'}


def test_get_portfolio_uses_demo_portfolio_endpoint(monkeypatch):
    settings = Settings(
        ETORO_ENV='demo',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)
    captured = {}

    def fake_get(path, params=None):
        captured['path'] = path
        captured['params'] = params
        return {'clientPortfolio': {'positions': []}}

    monkeypatch.setattr(client, '_get', fake_get)

    result = client.get_portfolio()

    assert result == {'clientPortfolio': {'positions': []}}
    assert captured['path'] == '/api/v1/trading/info/demo/portfolio'
    assert captured['params'] is None


def test_get_portfolio_uses_real_portfolio_endpoint(monkeypatch):
    settings = Settings(
        ETORO_ENV='real',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)
    captured = {}

    def fake_get(path, params=None):
        captured['path'] = path
        captured['params'] = params
        return {'clientPortfolio': {'positions': []}}

    monkeypatch.setattr(client, '_get', fake_get)

    result = client.get_portfolio()

    assert result == {'clientPortfolio': {'positions': []}}
    assert captured['path'] == '/api/v1/trading/info/portfolio'
    assert captured['params'] is None


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
        return {
            'orderId': 362406474,
            'referenceId': 'ref-1',
        }

    def fake_wait_for_executed_order(order_id):
        assert order_id == '362406474'
        return {
            'status': {
                'id': 1,
                'name': 'Executed',
            },
            'positionExecutions': [
                {
                    'positionId': 9001,
                    'state': 'open',
                }
            ],
        }

    monkeypatch.setattr(client, '_post', fake_post)
    monkeypatch.setattr(
        client,
        '_wait_for_executed_order',
        fake_wait_for_executed_order,
    )

    position_id = client.open_position(
        symbol='BTC',
        side='BUY',
        amount=5.0,
        stop_loss=60000.0,
        take_profit=62000.0,
    )

    assert position_id == '9001'
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
    assert client.position_instruments['9001'] == 100000


def test_etoro_close_position_sends_expected_payload_and_confirms_portfolio_closed(monkeypatch):
    settings = Settings(
        EAR_MODE='real',
        REAL_TRADING_ENABLED=True,
        ETORO_ENV='demo',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)
    client.position_instruments['9001'] = 100000
    captured = {}

    def fake_post(path, payload):
        captured['path'] = path
        captured['payload'] = payload
        return {
            'orderForClose': {
                'positionID': 9001,
                'instrumentID': 100000,
                'orderID': 362447424,
                'statusID': 1,
            },
            'token': 'close-token',
        }

    def fake_wait_until_position_closed(position_id):
        assert position_id == '9001'

    def fail_if_called(order_id):
        raise AssertionError(
            'close order lookup should not be called for accepted demo close response'
        )

    monkeypatch.setattr(client, '_post', fake_post)
    monkeypatch.setattr(client, '_wait_until_position_closed', fake_wait_until_position_closed)
    monkeypatch.setattr(client, '_wait_for_executed_order', fail_if_called)

    client.close_position('9001')

    assert captured['path'] == (
        '/api/v1/trading/execution/demo/market-close-orders/positions/9001'
    )
    assert captured['payload'] == {
        'InstrumentId': 100000,
        'UnitsToDeduct': None,
    }
    assert '9001' not in client.position_instruments


def test_etoro_close_position_falls_back_to_lookup_when_close_response_is_not_accepted(monkeypatch):
    settings = Settings(
        EAR_MODE='real',
        REAL_TRADING_ENABLED=True,
        ETORO_ENV='real',
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)
    client.position_instruments['9001'] = 100000
    captured = {}
    waited_orders = []
    confirmed_positions = []

    def fake_post(path, payload):
        captured['path'] = path
        captured['payload'] = payload
        return {
            'orderForClose': {
                'positionID': 9001,
                'instrumentID': 100000,
                'orderID': 362447424,
                'statusID': 0,
            },
            'token': 'close-token',
        }

    def fake_wait_for_executed_order(order_id):
        waited_orders.append(order_id)
        return {
            'status': {
                'id': 1,
                'name': 'Executed',
            },
            'positionsToClose': [9001],
            'positionExecutions': [
                {
                    'positionId': 9001,
                    'state': 'closed',
                }
            ],
        }

    def fake_wait_until_position_closed(position_id):
        confirmed_positions.append(position_id)

    monkeypatch.setattr(client, '_post', fake_post)
    monkeypatch.setattr(
        client,
        '_wait_for_executed_order',
        fake_wait_for_executed_order,
    )
    monkeypatch.setattr(client, '_wait_until_position_closed', fake_wait_until_position_closed)

    client.close_position('9001')

    assert captured['path'] == (
        '/api/v1/trading/execution/market-close-orders/positions/9001'
    )
    assert captured['payload'] == {
        'InstrumentId': 100000,
        'UnitsToDeduct': None,
    }
    assert waited_orders == ['362447424']
    assert confirmed_positions == ['9001']
    assert '9001' not in client.position_instruments


def test_extract_order_id_from_direct_order_response():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    order_id = client._extract_order_id(
        {
            'orderId': 362406474,
            'referenceId': 'ref-1',
        }
    )

    assert order_id == '362406474'


def test_extract_order_id_from_close_order_response():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    order_id = client._extract_order_id(
        {
            'orderForClose': {
                'positionID': 9001,
                'instrumentID': 100000,
                'orderID': 362447424,
            }
        }
    )

    assert order_id == '362447424'


def test_extract_reference_id_from_order_response():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    reference_id = client._extract_reference_id(
        {
            'orderId': 362406474,
            'referenceId': 'ref-1',
        }
    )

    assert reference_id == 'ref-1'


def test_extract_position_id_from_order_details():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    position_id = client._extract_position_id_from_order_details(
        {
            'status': {
                'id': 1,
                'name': 'Executed',
            },
            'positionExecutions': [
                {
                    'positionId': 9001,
                    'state': 'open',
                }
            ],
        }
    )

    assert position_id == '9001'


def test_extract_position_id_from_order_details_returns_none_when_missing():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    position_id = client._extract_position_id_from_order_details(
        {
            'status': {
                'id': 1,
                'name': 'Executed',
            },
            'positionExecutions': [],
        }
    )

    assert position_id is None


def test_extract_position_id_from_demo_legacy_positions():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    position_id = client._extract_position_id_from_order_details(
        {
            'statusID': 3,
            'errorCode': 0,
            'positions': [
                {
                    'positionID': 3549889123,
                    'isOpen': True,
                }
            ],
        }
    )

    assert position_id == '3549889123'


def test_order_is_executed_when_status_name_is_executed():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._is_order_executed(
        {
            'status': {
                'id': 1,
                'name': 'Executed',
            }
        }
    )


def test_order_is_executed_when_status_id_is_one():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._is_order_executed(
        {
            'status': {
                'id': 1,
                'name': 'SomethingElse',
            }
        }
    )


def test_order_is_executed_when_demo_status_id_is_one():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._is_order_executed({'statusID': 1})


def test_order_is_executed_when_demo_status_id_is_three_and_error_code_is_zero():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._is_order_executed(
        {
            'statusID': 3,
            'errorCode': 0,
            'positions': [
                {
                    'positionID': 3549889123,
                    'isOpen': True,
                }
            ],
        }
    )


def test_order_is_not_executed_when_status_is_pending():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert not client._is_order_executed(
        {
            'status': {
                'id': 2,
                'name': 'Pending',
            }
        }
    )


def test_order_is_rejected_when_error_code_is_non_zero():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._is_order_rejected(
        {
            'statusID': 4,
            'errorCode': 759,
            'errorMessage': 'manual Trading is disallowed for this instrument type(10:CRYPTO)',
        }
    )


def test_wait_for_executed_order_fails_fast_when_order_is_rejected(monkeypatch):
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)
    calls = []

    def fake_get_order_details(order_id):
        calls.append(order_id)
        return {
            'orderID': 362398636,
            'statusID': 4,
            'errorCode': 759,
            'errorMessage': 'manual Trading is disallowed for this instrument type(10:CRYPTO)',
        }

    monkeypatch.setattr(client, 'get_order_details', fake_get_order_details)

    with pytest.raises(RuntimeError, match='eToro order rejected'):
        client._wait_for_executed_order(
            order_id='362398636',
            attempts=10,
            delay_seconds=0,
        )

    assert calls == ['362398636']


def test_is_close_response_accepted_when_position_matches_and_status_is_one():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._is_close_response_accepted(
        {
            'orderForClose': {
                'positionID': 3549893989,
                'orderID': 362453867,
                'statusID': 1,
            }
        },
        '3549893989',
    )


def test_is_close_response_not_accepted_when_position_does_not_match():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert not client._is_close_response_accepted(
        {
            'orderForClose': {
                'positionID': 3549893989,
                'orderID': 362453867,
                'statusID': 1,
            }
        },
        'another-position',
    )


def test_is_close_response_not_accepted_when_status_is_not_one():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert not client._is_close_response_accepted(
        {
            'orderForClose': {
                'positionID': 3549893989,
                'orderID': 362453867,
                'statusID': 0,
            }
        },
        '3549893989',
    )


def test_contains_open_position_when_position_exists_in_client_portfolio():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert client._contains_open_position(
        {
            'clientPortfolio': {
                'positions': [
                    {
                        'positionID': 3549893989,
                        'instrumentID': 1001,
                    }
                ]
            }
        },
        '3549893989',
    )


def test_contains_open_position_returns_false_when_position_is_missing():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert not client._contains_open_position(
        {
            'clientPortfolio': {
                'positions': [
                    {
                        'positionID': 111,
                        'instrumentID': 1001,
                    }
                ]
            }
        },
        '3549893989',
    )


def test_contains_open_position_returns_false_when_position_is_explicitly_closed():
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    assert not client._contains_open_position(
        {
            'clientPortfolio': {
                'positions': [
                    {
                        'positionID': 3549893989,
                        'instrumentID': 1001,
                        'isOpen': False,
                    }
                ]
            }
        },
        '3549893989',
    )


def test_is_position_open_reads_portfolio(monkeypatch):
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    monkeypatch.setattr(
        client,
        'get_portfolio',
        lambda: {
            'clientPortfolio': {
                'positions': [
                    {
                        'positionID': 3549893989,
                        'instrumentID': 1001,
                    }
                ]
            }
        },
    )

    assert client.is_position_open('3549893989')


def test_wait_until_position_closed_returns_when_position_disappears(monkeypatch):
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)
    states = [True, False]

    def fake_is_position_open(position_id):
        assert position_id == '3549893989'
        return states.pop(0)

    monkeypatch.setattr(client, 'is_position_open', fake_is_position_open)

    client._wait_until_position_closed(
        position_id='3549893989',
        attempts=2,
        delay_seconds=0,
    )

    assert states == []


def test_wait_until_position_closed_raises_when_position_stays_open(monkeypatch):
    settings = Settings(
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    monkeypatch.setattr(client, 'is_position_open', lambda position_id: True)

    with pytest.raises(RuntimeError, match='still appears open'):
        client._wait_until_position_closed(
            position_id='3549893989',
            attempts=2,
            delay_seconds=0,
        )

def test_etoro_open_short_position_sends_stop_loss_rate(monkeypatch):
    settings = Settings(
        EAR_MODE='real',
        REAL_TRADING_ENABLED=True,
        ETORO_ENV='demo',
        BASE_CURRENCY='USD',
        SHORT_SELLING_ENABLED=True,
        SHORT_LEVERAGE=1,
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)
    captured = {}

    monkeypatch.setattr(client, '_find_instrument_id', lambda symbol: 1261)

    def fake_post(path, payload):
        captured['path'] = path
        captured['payload'] = payload
        return {
            'orderId': 362406475,
            'referenceId': 'ref-short-1',
        }

    def fake_wait_for_executed_order(order_id):
        assert order_id == '362406475'
        return {
            'status': {
                'id': 1,
                'name': 'Executed',
            },
            'positionExecutions': [
                {
                    'positionId': 9002,
                    'state': 'open',
                }
            ],
        }

    monkeypatch.setattr(client, '_post', fake_post)
    monkeypatch.setattr(
        client,
        '_wait_for_executed_order',
        fake_wait_for_executed_order,
    )

    position_id = client.open_position(
        symbol='SAF.PA',
        side='SELL',
        amount=497.26,
        stop_loss=337.4092,
        take_profit=334.8862,
    )

    assert position_id == '9002'
    assert captured['path'] == '/api/v2/trading/execution/demo/orders'
    assert captured['payload'] == {
        'action': 'open',
        'transaction': 'sellShort',
        'InstrumentID': 1261,
        'orderType': 'mkt',
        'leverage': 1,
        'amount': 497.26,
        'orderCurrency': 'usd',
        'settlementType': 'cfd',
        'StopLossRate': 337.4092,
    }
    assert client.position_instruments['9002'] == 1261

def test_etoro_buy_payload_does_not_include_short_only_fields():
    settings = Settings(
        EAR_MODE='real',
        REAL_TRADING_ENABLED=True,
        ETORO_ENV='demo',
        BASE_CURRENCY='USD',
        SHORT_SELLING_ENABLED=True,
        SHORT_LEVERAGE=1,
        ETORO_API_KEY='api-key',
        ETORO_USER_KEY='user-key',
    )

    client = EtoroClient(settings=settings)

    payload = client._build_open_order_payload(
        instrument_id=1234,
        side='BUY',
        amount=500.0,
        stop_loss=99.0,
        take_profit=101.0,
    )

    assert payload == {
        'action': 'open',
        'transaction': 'buy',
        'InstrumentID': 1234,
        'orderType': 'mkt',
        'leverage': 1,
        'amount': 500.0,
        'orderCurrency': 'usd',
    }