from app.brokers.etoro.endpoint_paths import (
    close_position_path,
    demo_order_details_path,
    demo_portfolio_path,
    open_order_path,
    real_order_lookup_path,
    real_portfolio_path,
)
from app.brokers.etoro.etoro_client import EtoroClient
from app.config.settings import Settings


def build_client(broker: str) -> EtoroClient:
    return EtoroClient(
        settings=Settings(
            BROKER=broker,
            ETORO_API_KEY='api-key',
            ETORO_USER_KEY='user-key',
        )
    )


def test_etoro_client_open_order_path_matches_endpoint_path_helper():
    demo_client = build_client('etoro_demo')
    live_client = build_client('etoro_live')

    assert demo_client._open_order_path() == open_order_path('demo')
    assert live_client._open_order_path() == open_order_path('live')


def test_etoro_client_close_position_path_matches_endpoint_path_helper():
    demo_client = build_client('etoro_demo')
    live_client = build_client('etoro_live')

    assert demo_client._close_position_path('123') == close_position_path('demo', '123')
    assert live_client._close_position_path('123') == close_position_path('live', '123')


def test_etoro_client_order_details_paths_match_endpoint_path_helpers():
    demo_client = build_client('etoro_demo')
    live_client = build_client('etoro_live')

    assert demo_client._demo_order_details_path('123') == demo_order_details_path('123')
    assert live_client._real_order_lookup_path() == real_order_lookup_path()


def test_etoro_client_portfolio_paths_match_endpoint_path_helpers():
    demo_client = build_client('etoro_demo')
    live_client = build_client('etoro_live')

    assert demo_client._demo_portfolio_path() == demo_portfolio_path()
    assert live_client._real_portfolio_path() == real_portfolio_path()
