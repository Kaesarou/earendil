from types import SimpleNamespace

from app.brokers.etoro.broker_environment import broker_environment_from_name
from app.brokers.etoro.etoro_client import EtoroClient


def test_etoro_client_environment_matches_helper_for_demo_broker():
    settings = SimpleNamespace(broker='etoro_demo')
    client = EtoroClient(settings=settings)

    assert client.env == broker_environment_from_name(settings.broker)


def test_etoro_client_environment_matches_helper_for_live_broker():
    settings = SimpleNamespace(broker='etoro_live')
    client = EtoroClient(settings=settings)

    assert client.env == broker_environment_from_name(settings.broker)
