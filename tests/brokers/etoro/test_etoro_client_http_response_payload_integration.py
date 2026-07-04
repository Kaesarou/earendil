from types import SimpleNamespace

import requests

from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.http_response_payload import response_payload


class FakeResponse:
    def __init__(self, *, content: bytes, payload: dict):
        self.status_code = 200
        self.content = content
        self._payload = payload
        self.text = str(payload)

    @property
    def ok(self) -> bool:
        return True

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        raise AssertionError('raise_for_status should not be called for ok responses')


def build_uninitialized_client() -> EtoroClient:
    client = object.__new__(EtoroClient)
    client.etoro_api_base_url = 'https://example.test'
    client.headers = {}
    client.settings = SimpleNamespace()
    return client


def test_etoro_client_post_empty_content_matches_response_payload_helper(monkeypatch):
    client = build_uninitialized_client()
    response = FakeResponse(content=b'', payload={'ignored': True})

    monkeypatch.setattr(requests, 'post', lambda *args, **kwargs: response)

    assert client._post('/path', {}) == response_payload(response)


def test_etoro_client_post_json_content_matches_response_payload_helper(monkeypatch):
    client = build_uninitialized_client()
    response = FakeResponse(content=b'{}', payload={'ok': True})

    monkeypatch.setattr(requests, 'post', lambda *args, **kwargs: response)

    assert client._post('/path', {}) == response_payload(response)
