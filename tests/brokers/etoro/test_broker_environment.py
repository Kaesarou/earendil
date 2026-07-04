from app.brokers.etoro.broker_environment import broker_environment_from_name


def test_broker_environment_from_demo_name():
    assert broker_environment_from_name('etoro_demo') == 'demo'


def test_broker_environment_from_live_name():
    assert broker_environment_from_name('etoro_live') == 'live'


def test_broker_environment_from_plain_name_returns_plain_value():
    assert broker_environment_from_name('demo') == 'demo'
