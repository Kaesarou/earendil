from app.brokers.base import BrokerClient
from app.brokers.cached_broker import CachedBrokerClient
from app.brokers.etoro_client import EtoroClient
from app.brokers.fake_broker import FakeBrokerClient
from app.config.settings import Settings


def with_api_cache(settings: Settings, broker: BrokerClient) -> BrokerClient:
    if not settings.api_cache_enabled:
        return broker
    return CachedBrokerClient(
        delegate=broker,
        market_snapshot_ttl_seconds=settings.market_snapshot_cache_ttl_seconds,
        account_equity_ttl_seconds=settings.account_equity_cache_ttl_seconds,
        position_status_ttl_seconds=settings.position_status_cache_ttl_seconds,
        batch_market_rates_enabled=settings.market_rates_batch_enabled,
        logging_enabled=settings.api_cache_logging_enabled,
    )


def build_market_data_broker(settings: Settings) -> BrokerClient:
    if settings.broker == 'etoro':
        return with_api_cache(settings, EtoroClient(settings=settings))
    if settings.broker == 'fake':
        return with_api_cache(settings, FakeBrokerClient(equity=50.0))
    raise ValueError(f'Unsupported market data broker: {settings.broker}')


def build_execution_broker(settings: Settings) -> BrokerClient:
    if settings.ear_mode == 'paper':
        return with_api_cache(settings, FakeBrokerClient(equity=50.0))
    if settings.ear_mode == 'real':
        return with_api_cache(settings, EtoroClient(settings=settings))
    raise ValueError(f'Unsupported execution mode: {settings.ear_mode}')
