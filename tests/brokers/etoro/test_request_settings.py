from app.brokers.etoro.request_settings import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    default_request_timeout_seconds,
)


def test_default_request_timeout_seconds():
    assert DEFAULT_REQUEST_TIMEOUT_SECONDS == 10
    assert default_request_timeout_seconds() == 10
