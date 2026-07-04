import pytest

from app.brokers.etoro.account_equity_mapper import extract_account_equity


def test_extract_account_equity_from_top_level_equity():
    equity = extract_account_equity(
        {
            'equity': 100000.25,
        }
    )

    assert equity == 100000.25


def test_extract_account_equity_from_client_portfolio_balance():
    equity = extract_account_equity(
        {
            'clientPortfolio': {
                'balance': 98765.43,
            }
        }
    )

    assert equity == 98765.43


def test_extract_account_equity_from_nested_available_balance():
    equity = extract_account_equity(
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
    equity = extract_account_equity(
        {
            'equity': 50000.0,
            'clientPortfolio': {
                'balance': 100000.0,
            },
        }
    )

    assert equity == 50000.0


def test_extract_account_equity_from_client_portfolio_credit():
    equity = extract_account_equity(
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


def test_extract_account_equity_raises_when_missing():
    with pytest.raises(ValueError, match='Unable to extract account equity'):
        extract_account_equity(
            {
                'clientPortfolio': {
                    'positions': [],
                },
            }
        )


def test_extract_account_equity_raises_when_zero():
    with pytest.raises(ValueError, match='Invalid eToro account equity'):
        extract_account_equity(
            {
                'equity': 0,
            }
        )
