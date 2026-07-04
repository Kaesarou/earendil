import pytest

from app.brokers.etoro.trade_side import (
    ensure_side_is_allowed,
    normalize_and_validate_side,
    normalize_side,
)


def test_normalize_side_strips_spaces_and_uppercases_value():
    assert normalize_side(' buy ') == 'BUY'
    assert normalize_side(' sell ') == 'SELL'


@pytest.mark.parametrize('side', ['BUY', 'SELL'])
def test_ensure_side_is_allowed_accepts_supported_sides(side: str):
    ensure_side_is_allowed(side)


def test_ensure_side_is_allowed_rejects_unsupported_side():
    with pytest.raises(ValueError, match='Unsupported side for eToro order'):
        ensure_side_is_allowed('HOLD')


def test_normalize_and_validate_side_returns_normalized_supported_side():
    assert normalize_and_validate_side(' buy ') == 'BUY'
    assert normalize_and_validate_side(' sell ') == 'SELL'


def test_normalize_and_validate_side_rejects_unsupported_side():
    with pytest.raises(ValueError, match='Unsupported side for eToro order'):
        normalize_and_validate_side('hold')
