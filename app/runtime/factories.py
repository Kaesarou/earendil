from app.brokers.base import BrokerClient
from app.brokers.cached_broker import CachedBrokerClient
from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.fake.fake_broker import FakeBrokerClient
from app.config.settings import Settings


def build_broker(settings: Settings) -> BrokerClient:
    if settings.broker == 'paper':
        return CachedBrokerClient(
            FakeBrokerClient(equity=50.0)
        )

    if settings.broker == 'etoro_demo' or settings.broker == 'etoro_live':
        return CachedBrokerClient(
            EtoroClient(settings=settings)
        )

    raise ValueError(f'Unsupported broker: {settings.broker}')
