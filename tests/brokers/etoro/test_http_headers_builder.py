from app.brokers.etoro.http_headers_builder import build_headers


def test_build_headers():
    assert build_headers(
        request_id='request-1',
        api_key='public-token',
        user_key='user-token',
    ) == {
        'x-request-id': 'request-1',
        'x-api-key': 'public-token',
        'x-user-key': 'user-token',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
