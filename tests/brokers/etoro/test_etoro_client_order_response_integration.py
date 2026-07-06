from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.order_response_parser import (
    extract_executed_position_details_list,
    extract_order_error_code,
    extract_order_error_message,
    extract_order_id,
    extract_position_id_from_order_details,
    extract_reference_id,
    has_executed_position_details,
    is_close_response_accepted,
    is_order_executed,
    is_order_rejected,
)
from app.config.settings import Settings


def build_client() -> EtoroClient:
    return EtoroClient(
        settings=Settings(
            ETORO_API_KEY='api-key',
            ETORO_USER_KEY='user-key',
        )
    )


def test_etoro_client_order_response_parsing_matches_parser():
    client = build_client()
    payload = {
        'orderForClose': {
            'positionID': 3549893989,
            'orderID': 362453867,
            'statusID': 1,
        },
        'referenceId': 'ref-1',
        'status': {
            'id': 1,
            'name': 'Executed',
            'errorCode': 0,
        },
    }

    assert client._extract_order_id(payload) == extract_order_id(payload)
    assert client._extract_reference_id(payload) == extract_reference_id(payload)
    assert client._is_order_executed(payload) == is_order_executed(payload)
    assert client._is_order_rejected(payload) == is_order_rejected(payload)
    assert client._is_close_response_accepted(payload, '3549893989') == is_close_response_accepted(payload, '3549893989')


def test_etoro_client_order_error_parsing_matches_parser():
    client = build_client()
    payload = {
        'status': {
            'id': 3,
            'name': 'Rejected',
            'errorCode': 759,
            'errorMessage': 'manual Trading is disallowed for this instrument type(10:CRYPTO)',
        }
    }

    assert client._extract_order_error_code(payload) == extract_order_error_code(payload)
    assert client._extract_order_error_message(payload) == extract_order_error_message(payload)
    assert client._is_order_executed(payload) == is_order_executed(payload)
    assert client._is_order_rejected(payload) == is_order_rejected(payload)


def test_etoro_client_position_execution_parsing_matches_parser():
    client = build_client()
    payload = {
        'status': {
            'id': 1,
            'name': 'Executed',
            'errorCode': 0,
        },
        'positionExecutions': [
            {
                'positionId': 9001,
                'state': 'open',
                'openingData': {
                    'avgPrice': 238.0,
                },
            }
        ],
    }

    assert client._extract_position_id_from_order_details(payload) == extract_position_id_from_order_details(payload)
    assert client._extract_executed_position_details_list(payload) == extract_executed_position_details_list(payload)
    assert client._has_executed_position_details(payload) == has_executed_position_details(payload)
