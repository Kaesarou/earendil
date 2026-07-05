from app.brokers.etoro.payload_collections import keep_dict_items
from app.brokers.etoro.scalar_extractors import extract_optional_int
from app.brokers.etoro.string_extractors import extract_optional_string


ORDER_ID_KEYS = ('orderId', 'OrderId', 'orderID', 'OrderID')
ORDER_ID_NESTED_KEYS = ('orderForClose', 'OrderForClose', 'data', 'Data', 'order', 'Order')
REFERENCE_ID_KEYS = ('referenceId', 'ReferenceId', 'referenceID', 'ReferenceID')
ORDER_ERROR_CODE_KEYS = ('errorCode',)
POSITION_ID_KEYS = ('positionId', 'PositionId', 'positionID', 'PositionID')
POSITION_EXECUTION_KEYS = ('positionExecutions', 'positions')
POSITION_NESTED_KEYS = ('position', 'Position', 'data', 'Data', 'order', 'Order')
CLOSE_STATUS_ID_KEYS = ('statusID', 'statusId')


def extract_order_id(payload: dict) -> str:
    order_id = extract_optional_string(payload, ORDER_ID_KEYS)
    if order_id is not None:
        return order_id

    for key in ORDER_ID_NESTED_KEYS:
        value = payload.get(key)
        if isinstance(value, dict):
            try:
                return extract_order_id(value)
            except ValueError:
                pass

    raise ValueError(f'Unable to extract order id from eToro response: {payload}')


def extract_reference_id(payload: dict) -> str | None:
    return extract_optional_string(payload, REFERENCE_ID_KEYS)


def extract_position_id(payload: dict) -> str | None:
    return extract_optional_string(payload, POSITION_ID_KEYS)


def extract_position_id_from_order_details(payload: dict) -> str | None:
    direct_position_id = extract_position_id(payload)

    if direct_position_id is not None:
        return direct_position_id

    for key in POSITION_EXECUTION_KEYS:
        positions = payload.get(key)
        if not isinstance(positions, list):
            continue

        for position in keep_dict_items(positions):
            position_id = extract_position_id(position)

            if position_id is not None:
                return position_id

    for key in POSITION_NESTED_KEYS:
        value = payload.get(key)
        if isinstance(value, dict):
            position_id = extract_position_id_from_order_details(value)
            if position_id is not None:
                return position_id

    return None


def extract_order_error_code(payload: dict) -> int | None:
    error_code = extract_optional_int(payload, ORDER_ERROR_CODE_KEYS)
    if error_code is not None:
        return error_code

    status = payload.get('status')
    if isinstance(status, dict):
        return extract_optional_int(status, ORDER_ERROR_CODE_KEYS)

    return None


def extract_order_error_message(payload: dict) -> str | None:
    error_message = payload.get('errorMessage')

    if error_message:
        return str(error_message)

    status = payload.get('status')
    if isinstance(status, dict):
        status_error_message = status.get('errorMessage')
        if status_error_message:
            return str(status_error_message)

    return None


def is_order_executed(payload: dict) -> bool:
    status = payload.get('status')

    if isinstance(status, dict):
        status_name = str(status.get('name', '')).lower()
        status_id = status.get('id')
        status_error_code = status.get('errorCode')

        if status_error_code not in (None, 0):
            return False

        if status_name == 'executed' or status_id == 1:
            return True

    error_code = payload.get('errorCode')
    if error_code not in (None, 0):
        return False

    status_id = payload.get('statusID')
    if status_id in (1, 3):
        return True

    return extract_position_id_from_order_details(payload) is not None


def is_order_rejected(payload: dict) -> bool:
    error_code = extract_order_error_code(payload)
    if error_code not in (None, 0):
        return True

    status = payload.get('status')
    if isinstance(status, dict):
        status_error_code = status.get('errorCode')
        if status_error_code not in (None, 0):
            return True

        status_name = str(status.get('name', '')).lower()
        if status_name in ('rejected', 'failed', 'cancelled', 'canceled', 'error'):
            return True

    return False


def is_close_response_accepted(payload: dict, position_id: str) -> bool:
    order_for_close = payload.get('orderForClose')

    if not isinstance(order_for_close, dict):
        return False

    response_position_id = extract_position_id(order_for_close)

    if str(response_position_id) != str(position_id):
        return False

    status_id = extract_optional_int(order_for_close, CLOSE_STATUS_ID_KEYS)

    return status_id == 1
