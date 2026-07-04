import pytest

from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.trade_side import ensure_side_is_allowed, normalize_side


def build_uninitialized_client() -> EtoroClient:
    return object.__new__(EtoroClient)


def test_etoro_client_normalize_side_matches_helper():
    client = build_uninitialized_client()

    assert client._normalize_side(' buy ') == normalize_side(' buy ')
    assert client._normalize_side(' sell ') == normalize_side(' sell ')


@pytest.mark.parametrize('side', ['BUY', 'SELL'])
def test_etoro_client_ensure_side_is_allowed_matches_helper_for_supported_sides(side: str):
    client = build_uninitialized_client()

    assert client._ensure_side_is_allowed(side) == ensure_side_is_allowed(side)


def test_etoro_client_ensure_side_is_allowed_matches_helper_for_unsupported_side():
    client = build_uninitialized_client()

    with pytest.raises(ValueError, match='Unsupported side for eToro order'):
        client._ensure_side_is_allowed('HOLD')

    with pytest.raises(ValueError, match='Unsupported side for eToro order'):
        ensure_side_is_allowed('HOLD')
