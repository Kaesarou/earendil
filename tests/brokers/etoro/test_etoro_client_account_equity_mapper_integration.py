from app.brokers.etoro.account_equity_mapper import (
    extract_account_equity,
    extract_optional_account_equity,
)
from app.brokers.etoro.etoro_client import EtoroClient


def build_uninitialized_client() -> EtoroClient:
    return object.__new__(EtoroClient)


def test_etoro_client_account_equity_matches_mapper_for_top_level_value():
    client = build_uninitialized_client()
    payload = {
        'equity': 100000.25,
    }

    assert client._extract_account_equity(payload) == extract_account_equity(payload)
    assert client._extract_optional_account_equity(payload) == extract_optional_account_equity(payload)


def test_etoro_client_account_equity_matches_mapper_for_nested_value():
    client = build_uninitialized_client()
    payload = {
        'data': {
            'portfolio': {
                'availableBalance': '12345.67',
            }
        }
    }

    assert client._extract_account_equity(payload) == extract_account_equity(payload)
    assert client._extract_optional_account_equity(payload) == extract_optional_account_equity(payload)


def test_etoro_client_optional_account_equity_matches_mapper_when_missing():
    client = build_uninitialized_client()
    payload = {
        'clientPortfolio': {
            'positions': [],
        },
    }

    assert client._extract_optional_account_equity(payload) == extract_optional_account_equity(payload)
