from types import SimpleNamespace

import requests

from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.request_settings import default_request_timeout_seconds


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
    client.etoro_api_base_url = 'https://example.test'
    client.settings = SimpleNamespace(
        etoro_api_key='public-token',
        etoro_user_key='user-token',
    )
    return client


def test_etoro_client_get_timeout_matches_request_settings(monkeypatch):
    client = build_uninitialized_client()
    captured = {}

    def fake_get(url, **kwargs):
        captured['timeout'] = kwargs['timeout']
        return FakeResponse()

    monkeypatch.setattr(requests, 'get', fake_get)

    assert client._get('/path') == {'ok': True}
    assert captured['timeout'] == default_request_timeout_seconds()


def test_etoro_client_post_timeout_matches_request_settings(monkeypatch):
    client = build_uninitialized_client()
    captured = {}

    def fake_post(url, **kwargs):
        captured['timeout'] = kwargs['timeout']
        return FakeResponse()

    monkeypatch.setattr(requests, 'post', fake_post)

    assert client._post('/path', {}) == {'ok': True}
    assert captured['timeout'] == default_request_timeout_seconds()
