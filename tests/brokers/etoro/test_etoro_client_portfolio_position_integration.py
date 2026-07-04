from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.portfolio_position_parser import (
    contains_open_position,
    extract_open_positions,
)
from app.config.settings import Settings


def build_client() -> EtoroClient:
    return EtoroClient(
        settings=Settings(
            ETORO_API_KEY='api-key',
            ETORO_USER_KEY='user-key',
        )
    )


def test_etoro_client_open_position_extraction_matches_parser():
    payload = {
        'clientPortfolio': {
            'positions': [
                {
                    'positionID': 3549893989,
                    'instrumentID': 1001,
                },
                {
                    'positionID': 111,
                    'instrumentID': 1002,
                    'isOpen': False,
                },
            ]
        }
    }
    client = build_client()

    assert client._extract_open_positions(payload) == extract_open_positions(payload)


def test_etoro_client_contains_open_position_matches_parser():
    payload = {
        'clientPortfolio': {
            'positions': [
                {
                    'positionID': 3549893989,
                    'instrumentID': 1001,
                },
                {
                    'positionID': 111,
                    'instrumentID': 1002,
                    'isOpen': False,
                },
            ]
        }
    }
    client = build_client()

    assert client._contains_open_position(
        payload,
        '3549893989',
    ) == contains_open_position(
        payload,
        '3549893989',
    )
    assert client._contains_open_position(
        payload,
        '111',
    ) == contains_open_position(
        payload,
        '111',
    )
    assert client._contains_open_position(
        payload,
        'missing-position',
    ) == contains_open_position(
        payload,
        'missing-position',
    )
