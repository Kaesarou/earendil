from app.brokers.etoro.etoro_client import EtoroClient
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


def build_uninitialized_client() -> EtoroClient:
    return object.__new__(EtoroClient)


def test_etoro_client_order_id_extractors_match_parser():
    client = build_uninitialized_client()
    payload = {
        'orderForClose': {
            'positionID': 9001,
            'instrumentID': 100000,
            'orderID': 362447424,
        }
    }

    assert client._extract_order_id(payload) == extract_order_id(payload)
    assert client._extract_reference_id(payload) == extract_reference_id(payload)


def test_etoro_client_position_id_extractor_matches_parser():
    client = build_uninitialized_client()
    payload = {
        'statusID': 3,
        'errorCode': 0,
        'positions': [
            {
                'positionID': 3549889123,
                'isOpen': True,
            }
        ],
    }

    assert client._extract_position_id_from_order_details(payload) == (
        extract_position_id_from_order_details(payload)
    )


def test_etoro_client_order_state_helpers_match_parser():
    client = build_uninitialized_client()
    payload = {
        'status': {
            'id': 1,
            'name': 'Executed',
            'errorCode': 0,
        },
        'positionExecutions': [
            {
                'positionId': 9001,
            }
        ],
    }

    assert client._is_order_executed(payload) == is_order_executed(payload)
    assert client._is_order_rejected(payload) == is_order_rejected(payload)


def test_etoro_client_order_error_helpers_match_parser():
    client = build_uninitialized_client()
    payload = {
        'status': {
            'errorCode': '759',
            'errorMessage': 'Rejected by broker',
        }
    }

    assert client._extract_order_error_code(payload) == extract_order_error_code(payload)
    assert client._extract_order_error_message(payload) == extract_order_error_message(payload)


def test_etoro_client_close_response_helper_matches_parser():
    client = build_uninitialized_client()
    payload = {
        'orderForClose': {
            'PositionId': '3549893989',
            'orderID': 362453867,
            'statusId': 1,
        }
    }

    assert client._is_close_response_accepted(payload, '3549893989') == (
        is_close_response_accepted(payload, '3549893989')
    )
