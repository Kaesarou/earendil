import pytest

from app.brokers.etoro.order_response_parser import (
    extract_order_error_code,
    extract_order_error_message,
    extract_order_id,
    extract_position_id_from_order_details,
    extract_reference_id,
    is_close_response_accepted,
    is_order_executed,
    is_order_rejected,
)


def test_extract_order_id_from_direct_order_response():
    assert extract_order_id(
        {
            'orderId': 362406474,
            'referenceId': 'ref-1',
        }
    ) == '362406474'


def test_extract_order_id_from_close_order_response():
    assert extract_order_id(
        {
            'orderForClose': {
                'positionID': 9001,
                'instrumentID': 100000,
                'orderID': 362447424,
            }
        }
    ) == '362447424'


def test_extract_order_id_raises_when_missing():
    with pytest.raises(ValueError, match='Unable to extract order id'):
        extract_order_id({'status': {'name': 'Executed'}})


def test_extract_reference_id_from_order_response():
    assert extract_reference_id(
        {
            'orderId': 362406474,
            'referenceId': 'ref-1',
        }
    ) == 'ref-1'


def test_extract_reference_id_returns_none_when_missing():
    assert extract_reference_id({'orderId': 362406474}) is None


def test_extract_position_id_from_order_details():
    position_id = extract_position_id_from_order_details(
        {
            'status': {
                'id': 1,
                'name': 'Executed',
            },
            'positionExecutions': [
                {
                    'positionId': 9001,
                    'state': 'open',
                }
            ],
        }
    )

    assert position_id == '9001'


def test_extract_position_id_from_demo_legacy_positions():
    position_id = extract_position_id_from_order_details(
        {
            'statusID': 3,
            'errorCode': 0,
            'positions': [
                {
                    'positionID': 3549889123,
                    'isOpen': True,
                }
            ],
        }
    )

    assert position_id == '3549889123'


def test_extract_position_id_from_nested_order_details():
    position_id = extract_position_id_from_order_details(
        {
            'data': {
                'order': {
                    'PositionID': 123456,
                }
            }
        }
    )

    assert position_id == '123456'


def test_extract_position_id_returns_none_when_missing():
    position_id = extract_position_id_from_order_details(
        {
            'status': {
                'id': 1,
                'name': 'Executed',
            },
            'positionExecutions': [],
        }
    )

    assert position_id is None


def test_order_is_executed_when_status_name_is_executed():
    assert is_order_executed(
        {
            'status': {
                'id': 2,
                'name': 'Executed',
            }
        }
    )


def test_order_is_executed_when_status_id_is_one():
    assert is_order_executed(
        {
            'status': {
                'id': 1,
                'name': 'SomethingElse',
            }
        }
    )


def test_order_is_executed_when_demo_status_id_is_one():
    assert is_order_executed({'statusID': 1})


def test_order_is_executed_when_demo_status_id_is_three_and_error_code_is_zero():
    assert is_order_executed(
        {
            'statusID': 3,
            'errorCode': 0,
            'positions': [
                {
                    'positionID': 3549889123,
                    'isOpen': True,
                }
            ],
        }
    )


def test_order_is_not_executed_when_status_is_pending():
    assert not is_order_executed(
        {
            'status': {
                'id': 2,
                'name': 'Pending',
            }
        }
    )


def test_order_is_not_executed_when_error_code_is_non_zero():
    assert not is_order_executed(
        {
            'statusID': 4,
            'errorCode': 759,
        }
    )


def test_order_is_rejected_when_error_code_is_non_zero():
    assert is_order_rejected(
        {
            'statusID': 4,
            'errorCode': 759,
            'errorMessage': 'manual Trading is disallowed for this instrument type(10:CRYPTO)',
        }
    )


def test_order_is_rejected_when_status_name_is_rejected():
    assert is_order_rejected(
        {
            'status': {
                'id': 4,
                'name': 'Rejected',
            }
        }
    )


def test_extract_order_error_code_from_top_level_payload():
    assert extract_order_error_code({'errorCode': '759'}) == 759


def test_extract_order_error_code_from_status_payload():
    assert extract_order_error_code({'status': {'errorCode': '759'}}) == 759


def test_extract_order_error_message_from_top_level_payload():
    assert extract_order_error_message({'errorMessage': 'Rejected by broker'}) == 'Rejected by broker'


def test_extract_order_error_message_from_status_payload():
    assert extract_order_error_message(
        {
            'status': {
                'errorMessage': 'Rejected by broker',
            }
        }
    ) == 'Rejected by broker'


def test_is_close_response_accepted_when_position_matches_and_status_is_one():
    assert is_close_response_accepted(
        {
            'orderForClose': {
                'positionID': 3549893989,
                'orderID': 362453867,
                'statusID': 1,
            }
        },
        '3549893989',
    )


def test_is_close_response_accepted_with_camel_case_position_and_status_id():
    assert is_close_response_accepted(
        {
            'orderForClose': {
                'PositionId': '3549893989',
                'orderID': 362453867,
                'statusId': 1,
            }
        },
        3549893989,
    )


def test_is_close_response_not_accepted_when_order_for_close_is_missing():
    assert not is_close_response_accepted({}, '3549893989')


def test_is_close_response_not_accepted_when_position_does_not_match():
    assert not is_close_response_accepted(
        {
            'orderForClose': {
                'positionID': 3549893989,
                'orderID': 362453867,
                'statusID': 1,
            }
        },
        'another-position',
    )


def test_is_close_response_not_accepted_when_status_is_not_one():
    assert not is_close_response_accepted(
        {
            'orderForClose': {
                'positionID': 3549893989,
                'orderID': 362453867,
                'statusID': 0,
            }
        },
        '3549893989',
    )
