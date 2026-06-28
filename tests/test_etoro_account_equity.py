import pytest

from app.brokers.etoro_client import EtoroClient
from app.config.settings import Settings


def build_client() -> EtoroClient:
    return EtoroClient(
        settings=Settings(
            ETORO_API_KEY='test-api-key',
            ETORO_USER_KEY='test-user-key',
        )
    )


def test_extract_account_equity_from_top_level_equity():
    client = build_client()

    equity = client._extract_account_equity(
        {
            'equity': 100000.25,
        }
    )

    assert equity == 100000.25


def test_extract_account_equity_from_client_portfolio_balance():
    client = build_client()

    equity = client._extract_account_equity(
        {
            'clientPortfolio': {
                'balance': 98765.43,
            }
        }
    )

    assert equity == 98765.43


def test_extract_account_equity_from_nested_available_balance():
    client = build_client()

    equity = client._extract_account_equity(
        {
            'data': {
                'portfolio': {
                    'availableBalance': '12345.67',
                }
            }
        }
    )

    assert equity == 12345.67


def test_extract_account_equity_prefers_top_level_value():
    client = build_client()

    equity = client._extract_account_equity(
        {
            'equity': 50000.0,
            'clientPortfolio': {
                'balance': 100000.0,
            },
        }
    )

    assert equity == 50000.0


def test_extract_account_equity_raises_when_missing():
    client = build_client()

    with pytest.raises(ValueError, match='Unable to extract account equity'):
        client._extract_account_equity(
            {
                'clientPortfolio': {
                    'positions': [],
                },
            }
        )


def test_extract_account_equity_raises_when_zero():
    client = build_client()

    with pytest.raises(ValueError, match='Invalid eToro account equity'):
        client._extract_account_equity(
            {
                'equity': 0,
            }
        )


def test_get_account_equity_uses_portfolio_payload(monkeypatch):
    client = build_client()

    monkeypatch.setattr(
        client,
        'get_portfolio',
        lambda: {
            'clientPortfolio': {
                'balance': 43210.0,
            }
        },
    )

    assert client.get_account_equity() == 43210.0

def test_extract_account_equity_from_client_portfolio_credit():
    client = build_client()

    equity = client._extract_account_equity(
        {
            'clientPortfolio': {
                'positions': [],
                'mirrors': [],
                'credit': 99973.89,
                'orders': [],
                'bonusCredit': 0.0,
            }
        }
    )

    assert equity == 99973.89