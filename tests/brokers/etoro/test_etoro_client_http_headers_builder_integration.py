from types import SimpleNamespace
from uuid import UUID

from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.http_headers_builder import build_headers


def build_uninitialized_client() -> EtoroClient:
    client = object.__new__(EtoroClient)
    client.settings = SimpleNamespace(
        etoro_api_key='public-token',
        etoro_user_key='user-token',
    )
    return client


def test_etoro_client_headers_match_builder():
    client = build_uninitialized_client()

    headers = client.headers
    UUID(headers['x-request-id'])

    assert headers == build_headers(
        request_id=headers['x-request-id'],
        api_key='public-token',
        user_key='user-token',
    )
