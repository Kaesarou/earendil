import pytest

from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.scalar_extractors import (
    extract_float,
    extract_int,
    extract_optional_float,
    extract_optional_int,
)


def build_uninitialized_client() -> EtoroClient:
    return object.__new__(EtoroClient)


def test_etoro_client_extract_float_matches_helper():
    client = build_uninitialized_client()
    payload = {'Bid': '10.5'}
    keys = ('Bid', 'bid')

    assert client._extract_float(payload, keys) == extract_float(payload, keys)


def test_etoro_client_extract_optional_float_matches_helper():
    client = build_uninitialized_client()
    payload = {'Bid': '0'}
    keys = ('Bid', 'bid')

    assert client._extract_optional_float(payload, keys) == extract_optional_float(payload, keys)


def test_etoro_client_extract_float_missing_error_matches_helper():
    client = build_uninitialized_client()
    payload = {}
    keys = ('Bid', 'bid')

    with pytest.raises(ValueError, match='Unable to extract required float'):
        client._extract_float(payload, keys)

    with pytest.raises(ValueError, match='Unable to extract required float'):
        extract_float(payload, keys)


def test_etoro_client_extract_int_matches_helper():
    client = build_uninitialized_client()
    payload = {'instrumentID': '1001'}
    keys = ('instrumentID', 'instrumentId')

    assert client._extract_int(payload, keys) == extract_int(payload, keys)


def test_etoro_client_extract_optional_int_matches_helper():
    client = build_uninitialized_client()
    payload = {'instrumentID': '0'}
    keys = ('instrumentID', 'instrumentId')

    assert client._extract_optional_int(payload, keys) == extract_optional_int(payload, keys)


def test_etoro_client_extract_int_missing_error_matches_helper():
    client = build_uninitialized_client()
    payload = {}
    keys = ('instrumentID', 'instrumentId')

    with pytest.raises(ValueError, match='Unable to extract required int'):
        client._extract_int(payload, keys)

    with pytest.raises(ValueError, match='Unable to extract required int'):
        extract_int(payload, keys)
