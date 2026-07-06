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


def filled_payload(*, with_position_details: bool) -> dict:
    payload = {
        'status': {
            'id': 3,
            'name': 'Filled',
            'errorCode': 0,
        }
    }
    if with_position_details:
        payload['positionExecutions'] = [
            {
                'positionId': 9001,
                'state': 'open',
                'openingData': {'avgPrice': 238.0},
            }
        ]
    return payload


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
    payload = filled_payload(with_position_details=True)

    assert client._extract_position_id_from_order_details(payload) == extract_position_id_from_order_details(payload)
    assert client._extract_executed_position_details_list(payload) == extract_executed_position_details_list(payload)
    assert client._has_executed_position_details(payload) == has_executed_position_details(payload)


def test_wait_for_executed_order_waits_for_filled_position_details(monkeypatch):
    client = build_client()
    responses = [
        filled_payload(with_position_details=False),
        filled_payload(with_position_details=True),
    ]
    seen_order_ids = []

    def fake_get_order_details(order_id: str):
        seen_order_ids.append(order_id)
        return responses.pop(0)

    monkeypatch.setattr(client, 'get_order_details', fake_get_order_details)

    details = client._wait_for_executed_order(
        'order-123',
        attempts=2,
        delay_seconds=0,
        require_position_details=True,
    )

    assert details == filled_payload(with_position_details=True)
    assert seen_order_ids == ['order-123', 'order-123']


def test_wait_for_executed_order_accepts_filled_close_without_position_details(monkeypatch):
    client = build_client()
    monkeypatch.setattr(
        client,
        'get_order_details',
        lambda order_id: filled_payload(with_position_details=False),
    )

    details = client._wait_for_executed_order(
        'close-order-123',
        attempts=1,
        delay_seconds=0,
        require_position_details=False,
    )

    assert details == filled_payload(with_position_details=False)
