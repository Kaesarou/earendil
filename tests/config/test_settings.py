import pytest
from pydantic import ValidationError

from app.config.settings import Settings


def test_watchlist_symbols_parses_comma_separated_symbols():
    settings = Settings(
        WATCHLIST='AAPL,MSFT,AMZN',
    )

    assert settings.watchlist_symbols() == ['AAPL', 'MSFT', 'AMZN']


def test_watchlist_symbols_strips_spaces_and_uppercases_symbols():
    settings = Settings(
        WATCHLIST=' aapl, msft , amzn ',
    )

    assert settings.watchlist_symbols() == ['AAPL', 'MSFT', 'AMZN']


def test_watchlist_symbols_removes_duplicates_while_preserving_order():
    settings = Settings(
        WATCHLIST='AAPL,MSFT,AAPL,AMZN,MSFT',
    )

    assert settings.watchlist_symbols() == ['AAPL', 'MSFT', 'AMZN']


def test_watchlist_symbols_raises_when_no_symbol_can_be_resolved():
    settings = Settings(
        WATCHLIST=' , , ',
    )

    with pytest.raises(ValueError, match='Watchlist cannot be empty'):
        settings.watchlist_symbols()


def test_unknown_runtime_setting_is_rejected():
    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        Settings(UNSUPPORTED_SETTING='value')
