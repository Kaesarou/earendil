from app.brokers.etoro.http_retry_policy import (
    default_get_max_attempts,
    is_retryable_http_status,
    retryable_http_status_codes,
)


def test_default_get_max_attempts():
    assert default_get_max_attempts() == 3


def test_retryable_http_status_codes_returns_copy():
    statuses = retryable_http_status_codes()
    statuses.add(418)

    assert retryable_http_status_codes() == {429, 500, 502, 503, 504}


def test_is_retryable_http_status():
    assert is_retryable_http_status(429) is True
    assert is_retryable_http_status(500) is True
    assert is_retryable_http_status(504) is True
    assert is_retryable_http_status(400) is False
    assert is_retryable_http_status(418) is False
