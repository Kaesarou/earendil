from app.brokers.base import BrokerClient
from app.brokers.cached_broker import CachedBrokerClient
from app.brokers.etoro_client import EtoroClient
from app.brokers.fake_broker import FakeBrokerClient
from app.config.settings import Settings


def with_api_cache(settings: Settings, broker: BrokerClient) -> BrokerClient:
    return CachedBrokerClient(
        delegate=broker,
        market_snapshot_ttl_seconds=settings.market_snapshot_cache_ttl_seconds,
        account_equity_ttl_seconds=settings.account_equity_cache_ttl_seconds,
        position_status_ttl_seconds=settings.position_status_cache_ttl_seconds,
        logging_enabled=settings.api_cache_logging_enabled,
    )

def build_broker(settings: Settings) -> BrokerClient:
    if settings.broker == 'paper':
        return with_api_cache(settings, FakeBrokerClient(equity=50.0))

    if settings.broker == 'etoro_demo' or settings.broker == 'etoro_live':
        return with_api_cache(settings, EtoroClient(settings=settings))

    raise ValueError(f'Unsupported broker: {settings.broker}')
