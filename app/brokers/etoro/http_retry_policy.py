DEFAULT_GET_MAX_ATTEMPTS = 3
RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}


def default_get_max_attempts() -> int:
    return DEFAULT_GET_MAX_ATTEMPTS


def retryable_http_status_codes() -> set[int]:
    return set(RETRYABLE_HTTP_STATUS_CODES)


def is_retryable_http_status(status_code: int) -> bool:
    return status_code in RETRYABLE_HTTP_STATUS_CODES
