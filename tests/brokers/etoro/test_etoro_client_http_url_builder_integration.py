from types import SimpleNamespace

import requests

from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.http_url_builder import build_http_url


class FakeResponse:
    status_code = 200
    content = b'{}'
    text = '{}'

    @property
    def ok(self) -> bool:
        return True

    def json(self) -> dict:
        return {'ok': True}

    def raise_for_status(self) -> None:
        raise AssertionError('raise_for_status should not be called for ok responses')


def build_uninitialized_client() -> EtoroClient:
    client = object.__new__(EtoroClient)
    client.etoro_api_base_url = 'https://example.test/'
    client.settings = SimpleNamespace(
        etoro_api_key='api-key',
        etoro_user_key='user-key',
    )
    return client


def test_etoro_client_get_url_matches_helper(monkeypatch):
    client = build_uninitialized_client()
    captured = {}

    def fake_get(url, **kwargs):
        captured['url'] = url
        return FakeResponse()

    monkeypatch.setattr(requests, 'get', fake_get)

    assert client._get('/path') == {'ok': True}
    assert captured['url'] == build_http_url(client.etoro_api_base_url, '/path')


def test_etoro_client_post_url_matches_helper(monkeypatch):
    client = build_uninitialized_client()
    captured = {}

    def fake_post(url, **kwargs):
        captured['url'] = url
        return FakeResponse()

    monkeypatch.setattr(requests, 'post', fake_post)

    assert client._post('/path', {}) == {'ok': True}
    assert captured['url'] == build_http_url(client.etoro_api_base_url, '/path')
