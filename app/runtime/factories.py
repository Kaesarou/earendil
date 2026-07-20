from dataclasses import dataclass

from app.brokers.base import BrokerClient
from app.brokers.cached_broker import CachedBrokerClient
from app.brokers.etoro.market_data_client import EtoroRestMarketDataClient
from app.brokers.etoro.resilient_client import ResilientEtoroClient
from app.brokers.etoro.websocket_feed import EtoroWebSocketMarketDataFeed
from app.brokers.fake.fake_broker import FakeBrokerClient
from app.config.settings import Settings
from app.market_data.contracts import LiveMarketDataFeed, RestMarketDataClient
from app.market_data.models import MarketDataSource
from app.market_data.polling_feed import PollingMarketDataFeed


@dataclass(frozen=True)
class RuntimeClients:
    execution_broker: BrokerClient
    rest_market_data: RestMarketDataClient
    live_market_data: LiveMarketDataFeed


def build_runtime_clients(settings: Settings) -> RuntimeClients:
    if settings.broker == 'paper':
        fake = FakeBrokerClient(equity=50.0)
        return RuntimeClients(
            execution_broker=CachedBrokerClient(fake),
            rest_market_data=fake,
            live_market_data=PollingMarketDataFeed(
                client=fake,
                interval_seconds=settings.poll_interval_seconds,
                queue_capacity=settings.market_data_queue_capacity,
                source=MarketDataSource.PAPER,
            ),
        )

    if settings.broker in {'etoro_demo', 'etoro_live'}:
        etoro = ResilientEtoroClient(settings=settings)
        market_data = EtoroRestMarketDataClient(
            etoro,
            instrument_id_cache_path=settings.instrument_id_cache_path,
            resolution_min_interval_seconds=(
                settings.instrument_resolution_min_interval_seconds
            ),
        )
        mode = settings.market_data_mode.strip().lower()
        if mode not in {'auto', 'websocket', 'polling'}:
            raise ValueError(
                f'Unsupported MARKET_DATA_MODE: {settings.market_data_mode}'
            )
        live_feed: LiveMarketDataFeed
        if mode in {'auto', 'websocket'}:
            live_feed = EtoroWebSocketMarketDataFeed(
                api_key=settings.etoro_api_key,
                user_key=settings.etoro_user_key,
                rest_client=market_data,
                queue_capacity=settings.market_data_queue_capacity,
                global_silence_seconds=settings.ws_global_silence_seconds,
            )
        else:
            live_feed = PollingMarketDataFeed(
                client=market_data,
                interval_seconds=settings.poll_interval_seconds,
                queue_capacity=settings.market_data_queue_capacity,
                source=MarketDataSource.REST_POLLING,
            )
        return RuntimeClients(
            execution_broker=CachedBrokerClient(etoro),
            rest_market_data=market_data,
            live_market_data=live_feed,
        )

    raise ValueError(f'Unsupported broker: {settings.broker}')


def build_broker(settings: Settings) -> BrokerClient:
    """Compatibility entry point for code that only needs execution services."""
    return build_runtime_clients(settings).execution_broker
