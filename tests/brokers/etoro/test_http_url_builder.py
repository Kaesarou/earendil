from app.brokers.etoro.http_url_builder import build_http_url


def test_build_http_url_joins_base_url_and_path():
    assert build_http_url('https://example.test', '/path') == 'https://example.test/path'


def test_build_http_url_strips_duplicate_slashes():
    assert build_http_url('https://example.test/', '/path') == 'https://example.test/path'
    assert build_http_url('https://example.test', 'path') == 'https://example.test/path'
    assert build_http_url('https://example.test/', 'path') == 'https://example.test/path'
