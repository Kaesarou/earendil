import pytest
import requests

from app.brokers.etoro.http_failure import is_http_success, raise_for_failed_response


class FakeResponse:
    def __init__(self, *, ok: bool):
        self.ok = ok

    def raise_for_status(self) -> None:
        raise requests.HTTPError('failed')


def test_is_http_success_returns_response_ok_flag():
    assert is_http_success(FakeResponse(ok=True)) is True
    assert is_http_success(FakeResponse(ok=False)) is False


def test_raise_for_failed_response_does_nothing_for_success():
    raise_for_failed_response(FakeResponse(ok=True))


def test_raise_for_failed_response_raises_for_failure():
    with pytest.raises(requests.HTTPError):
        raise_for_failed_response(FakeResponse(ok=False))
