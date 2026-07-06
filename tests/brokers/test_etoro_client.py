import pytest

from app.brokers.etoro.etoro_client import EtoroClient
from app.config.settings import Settings


def build_settings(broker: str = 'etoro_demo') -> Settings:
    return Settings(BROKER=broker, ETORO_API_KEY='api-key', ETORO_USER_KEY='user-key')


def test_find_instrument_id_uses_exact_symbol_match(monkeypatch):
    client = EtoroClient(settings=build_settings())

    def fake_get(path, params=None):
        return {
            'items': [
                {'internalSymbolFull': 'BTCA', 'internalInstrumentDisplayName': 'Bitcoin / VAULTA', 'internalInstrumentId': 100134},
                {'internalSymbolFull': 'BTC', 'internalInstrumentDisplayName': 'Bitcoin', 'internalInstrumentId': 100000},
            ]
        }

    monkeypatch.setattr(client, '_get', fake_get)

    assert client._find_instrument_id('BTC') == 100000


def test_etoro_headers_include_required_keys():
    client = EtoroClient(settings=build_settings())

    headers = client.headers

    assert headers['x-api-key'] == 'api-key'
    assert headers['x-user-key'] == 'user-key'
    assert 'x-request-id' in headers
    assert headers['Content-Type'] == 'application/json'
    assert headers['Accept'] == 'application/json'


def test_to_market_snapshot_uses_mid_price_when_last_is_missing():
    client = EtoroClient(settings=build_settings())
    client.symbol_by_instrument_id = {1: 'BTC'}

    snapshot = client._to_market_snapshot(symbol='BTC', rates_payload={'rates': [{'instrumentID': 1, 'Bid': 100.0, 'Ask': 102.0}]})

    assert snapshot.symbol == 'BTC'
    assert snapshot.bid == 100.0
    assert snapshot.ask == 102.0
    assert snapshot.last == 101.0


def test_etoro_open_order_path_uses_demo_endpoint_when_env_is_demo():
    assert EtoroClient(settings=build_settings('etoro_demo'))._open_order_path() == '/api/v2/trading/execution/demo/orders'


def test_etoro_open_order_path_uses_real_endpoint_when_env_is_real():
    assert EtoroClient(settings=build_settings('etoro_live'))._open_order_path() == '/api/v2/trading/execution/orders'


def test_etoro_close_position_path_uses_demo_endpoint_when_env_is_demo():
    assert EtoroClient(settings=build_settings('etoro_demo'))._close_position_path('123') == '/api/v1/trading/execution/demo/market-close-orders/positions/123'


def test_etoro_close_position_path_uses_real_endpoint_when_env_is_real():
    assert EtoroClient(settings=build_settings('etoro_live'))._close_position_path('123') == '/api/v1/trading/execution/market-close-orders/positions/123'


def test_etoro_demo_order_lookup_path():
    assert EtoroClient(settings=build_settings('etoro_demo'))._order_lookup_path() == '/api/v2/trading/info/demo/orders:lookup'


def test_etoro_real_order_lookup_path():
    assert EtoroClient(settings=build_settings('etoro_live'))._order_lookup_path() == '/api/v2/trading/info/orders:lookup'


def test_etoro_demo_portfolio_path():
    assert EtoroClient(settings=build_settings('etoro_demo'))._demo_portfolio_path() == '/api/v1/trading/info/demo/portfolio'


def test_etoro_real_portfolio_path():
    assert EtoroClient(settings=build_settings('etoro_live'))._real_portfolio_path() == '/api/v1/trading/info/portfolio'


def test_get_order_details_uses_demo_v2_order_lookup_endpoint(monkeypatch):
    client = EtoroClient(settings=build_settings('etoro_demo'))
    captured = {}

    def fake_get(path, params=None):
        captured['path'] = path
        captured['params'] = params
        return {'orderId': 123}

    monkeypatch.setattr(client, '_get', fake_get)

    assert client.get_order_details('123') == {'orderId': 123}
    assert captured['path'] == '/api/v2/trading/info/demo/orders:lookup'
    assert captured['params'] == {'orderId': '123'}


def test_get_order_details_uses_real_order_lookup_endpoint(monkeypatch):
    client = EtoroClient(settings=build_settings('etoro_live'))
    captured = {}

    def fake_get(path, params=None):
        captured['path'] = path
        captured['params'] = params
        return {'orderId': 123}

    monkeypatch.setattr(client, '_get', fake_get)

    assert client.get_order_details('123') == {'orderId': 123}
    assert captured['path'] == '/api/v2/trading/info/orders:lookup'
    assert captured['params'] == {'orderId': '123'}


def test_get_portfolio_uses_demo_portfolio_endpoint(monkeypatch):
    client = EtoroClient(settings=build_settings('etoro_demo'))
    captured = {}

    def fake_get(path, params=None):
        captured['path'] = path
        captured['params'] = params
        return {'clientPortfolio': {'positions': []}}

    monkeypatch.setattr(client, '_get', fake_get)

    assert client.get_portfolio() == {'clientPortfolio': {'positions': []}}
    assert captured['path'] == '/api/v1/trading/info/demo/portfolio'
    assert captured['params'] is None


def test_get_portfolio_uses_real_portfolio_endpoint(monkeypatch):
    client = EtoroClient(settings=build_settings('etoro_live'))
    captured = {}

    def fake_get(path, params=None):
        captured['path'] = path
        captured['params'] = params
        return {'clientPortfolio': {'positions': []}}

    monkeypatch.setattr(client, '_get', fake_get)

    assert client.get_portfolio() == {'clientPortfolio': {'positions': []}}
    assert captured['path'] == '/api/v1/trading/info/portfolio'
    assert captured['params'] is None


def test_etoro_open_position_sends_expected_demo_order_payload(monkeypatch):
    client = EtoroClient(settings=Settings(BROKER='etoro_demo', BASE_CURRENCY='USD', ETORO_API_KEY='api-key', ETORO_USER_KEY='user-key'))
    captured = {}
    monkeypatch.setattr(client, '_find_instrument_id', lambda symbol: 100000)

    def fake_post(path, payload):
        captured['path'] = path
        captured['payload'] = payload
        return {'orderId': 362406474, 'referenceId': 'ref-1'}

    def fake_wait_for_executed_order(order_id, require_position_details=True):
        assert order_id == '362406474'
        assert require_position_details is True
        return {
            'status': {'id': 1, 'name': 'Executed', 'errorCode': 0},
            'positionExecutions': [{'positionId': 9001, 'state': 'open', 'openingData': {'avgPrice': 238.0}}],
        }

    monkeypatch.setattr(client, '_post', fake_post)
    monkeypatch.setattr(client, '_wait_for_executed_order', fake_wait_for_executed_order)

    result = client.open_position(symbol='BTC', side='BUY', amount=5.0, stop_loss=60000.0, take_profit=62000.0)

    assert result.position_id == '9001'
    assert result.executed_entry_price == 238.0
    assert captured['path'] == '/api/v2/trading/execution/demo/orders'
    assert captured['payload'] == {'action': 'open', 'transaction': 'buy', 'InstrumentID': 100000, 'orderType': 'mkt', 'leverage': 1, 'amount': 5.0, 'orderCurrency': 'usd'}
    assert client.position_instruments['9001'] == 100000


def test_etoro_open_position_rejects_multiple_position_executions(monkeypatch):
    client = EtoroClient(settings=build_settings('etoro_demo'))
    monkeypatch.setattr(client, '_find_instrument_id', lambda symbol: 100000)
    monkeypatch.setattr(client, '_post', lambda path, payload: {'orderId': 362406474, 'referenceId': 'ref-1'})

    def fake_wait_for_executed_order(order_id, require_position_details=True):
        return {
            'status': {'id': 1, 'name': 'Executed', 'errorCode': 0},
            'positionExecutions': [
                {'positionId': 9001, 'openingData': {'avgPrice': 238.0}},
                {'positionId': 9002, 'openingData': {'avgPrice': 239.0}},
            ],
        }

    monkeypatch.setattr(client, '_wait_for_executed_order', fake_wait_for_executed_order)

    with pytest.raises(RuntimeError, match='unsupported position execution count'):
        client.open_position(symbol='BTC', side='BUY', amount=5.0, stop_loss=60000.0, take_profit=62000.0)


def test_etoro_close_position_sends_expected_payload_and_confirms_portfolio_closed(monkeypatch):
    client = EtoroClient(settings=build_settings('etoro_demo'))
    client.position_instruments['9001'] = 100000
    captured = {}

    def fake_post(path, payload):
        captured['path'] = path
        captured['payload'] = payload
        return {'orderForClose': {'positionID': 9001, 'instrumentID': 100000, 'orderID': 362447424, 'statusID': 1}, 'token': 'close-token'}

    monkeypatch.setattr(client, '_post', fake_post)
    monkeypatch.setattr(client, '_wait_until_position_closed', lambda position_id: None)
    monkeypatch.setattr(client, '_wait_for_executed_order', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('lookup should not be called')))

    client.close_position('9001')

    assert captured['path'] == '/api/v1/trading/execution/demo/market-close-orders/positions/9001'
    assert captured['payload'] == {'InstrumentId': 100000, 'UnitsToDeduct': None}
    assert '9001' not in client.position_instruments


def test_etoro_close_position_falls_back_to_lookup_when_close_response_is_not_accepted(monkeypatch):
    client = EtoroClient(settings=build_settings('etoro_live'))
    client.position_instruments['9001'] = 100000
    captured = {}
    waited_orders = []
    confirmed_positions = []

    def fake_post(path, payload):
        captured['path'] = path
        captured['payload'] = payload
        return {'orderForClose': {'positionID': 9001, 'instrumentID': 100000, 'orderID': 362447424, 'statusID': 0}, 'token': 'close-token'}

    def fake_wait_for_executed_order(order_id, require_position_details=True):
        waited_orders.append((order_id, require_position_details))
        return {'status': {'id': 1, 'name': 'Executed', 'errorCode': 0}, 'positionsToClose': [9001]}

    def fake_wait_until_position_closed(position_id):
        confirmed_positions.append(position_id)

    monkeypatch.setattr(client, '_post', fake_post)
    monkeypatch.setattr(client, '_wait_for_executed_order', fake_wait_for_executed_order)
    monkeypatch.setattr(client, '_wait_until_position_closed', fake_wait_until_position_closed)

    client.close_position('9001')

    assert captured['path'] == '/api/v1/trading/execution/market-close-orders/positions/9001'
    assert captured['payload'] == {'InstrumentId': 100000, 'UnitsToDeduct': None}
    assert waited_orders == [('362447424', False)]
    assert confirmed_positions == ['9001']
    assert '9001' not in client.position_instruments
