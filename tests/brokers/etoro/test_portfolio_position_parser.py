from app.brokers.etoro.portfolio_position_parser import (
    contains_open_position,
    extract_open_positions,
)


def test_extract_open_positions_from_client_portfolio():
    payload = {
        'clientPortfolio': {
            'positions': [
                {
                    'positionID': 3549893989,
                    'instrumentID': 1001,
                },
                'ignored-non-dict',
            ]
        }
    }

    assert extract_open_positions(payload) == [
        {
            'positionID': 3549893989,
            'instrumentID': 1001,
        }
    ]


def test_extract_open_positions_from_top_level_positions():
    payload = {
        'positions': [
            {
                'positionId': 3549893989,
                'instrumentID': 1001,
            }
        ]
    }

    assert extract_open_positions(payload) == [
        {
            'positionId': 3549893989,
            'instrumentID': 1001,
        }
    ]


def test_extract_open_positions_from_nested_data_payload():
    payload = {
        'data': {
            'clientPortfolio': {
                'positions': [
                    {
                        'PositionID': 3549893989,
                        'instrumentID': 1001,
                    }
                ]
            }
        }
    }

    assert extract_open_positions(payload) == [
        {
            'PositionID': 3549893989,
            'instrumentID': 1001,
        }
    ]


def test_extract_open_positions_returns_empty_list_when_missing():
    assert extract_open_positions({'clientPortfolio': {'orders': []}}) == []


def test_contains_open_position_when_position_exists_in_client_portfolio():
    assert contains_open_position(
        {
            'clientPortfolio': {
                'positions': [
                    {
                        'positionID': 3549893989,
                        'instrumentID': 1001,
                    }
                ]
            }
        },
        '3549893989',
    )


def test_contains_open_position_accepts_position_id_key_variants():
    assert contains_open_position(
        {
            'positions': [
                {
                    'PositionId': 3549893989,
                    'instrumentID': 1001,
                }
            ]
        },
        '3549893989',
    )


def test_contains_open_position_returns_false_when_position_is_missing():
    assert not contains_open_position(
        {
            'clientPortfolio': {
                'positions': [
                    {
                        'positionID': 111,
                        'instrumentID': 1001,
                    }
                ]
            }
        },
        '3549893989',
    )


def test_contains_open_position_returns_false_when_position_is_explicitly_closed():
    assert not contains_open_position(
        {
            'clientPortfolio': {
                'positions': [
                    {
                        'positionID': 3549893989,
                        'instrumentID': 1001,
                        'isOpen': False,
                    }
                ]
            }
        },
        '3549893989',
    )


def test_contains_open_position_treats_missing_is_open_as_open():
    assert contains_open_position(
        {
            'clientPortfolio': {
                'positions': [
                    {
                        'positionID': 3549893989,
                        'instrumentID': 1001,
                    }
                ]
            }
        },
        '3549893989',
    )
