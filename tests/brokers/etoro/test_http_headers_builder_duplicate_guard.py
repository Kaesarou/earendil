from app.brokers.etoro.http_headers_builder import build_headers


def test_temporary_duplicate_guard():
    assert build_headers(
        request_id='request-1',
        api_key='public-token',
        user_key='user-token',
    )['Accept'] == 'application/json'
