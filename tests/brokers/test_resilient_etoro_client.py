from datetime import datetime, timezone

import pytest
import requests

from app.brokers.base import (
    ClosePositionRejectedError,
    ClosePositionSubmissionUnknownError,
)
from app.brokers.etoro.order_confirmation_error import (
    EtoroOrderConfirmationUnknownError,
)
from app.brokers.etoro.resilient_client import ResilientEtoroClient
from app.config.settings import Settings


def settings() -> Settings:
    return Settings.model_construct(
        broker='etoro_demo',
        base_currency='USD',
        etoro_sellshort_safety_sl_buffer_percent=0.30,
        etoro_api_key='api',
        etoro_user_key='user',
    )


def test_accepted_order_with_unavailable_lookup_preserves_identifiers(monkeypatch):
    client = ResilientEtoroClient(settings=settings())
    monkeypatch.setattr(client, '_find_instrument_id', lambda symbol: 100)
    monkeypatch.setattr(
        client,
        '_build_open_order_payload',
        lambda **kwargs: {
            'transaction': 'OpenBuy',
            'StopLossRate': None,
            'TakeProfitRate': None,
            'leverage': 1,
        },
    )
    monkeypatch.setattr(
        client,
        '_post',
        lambda path, payload: {
            'orderId': 'order-1',
            'referenceId': 'reference-1',
        },
    )

    def unavailable(*args, **kwargs):
        raise RuntimeError('Order category not found')

    monkeypatch.setattr(client, '_wait_for_executed_order', unavailable)

    with pytest.raises(EtoroOrderConfirmationUnknownError) as caught:
        client.open_position(
            symbol='BTC',
            side='BUY',
            amount=100.0,
            stop_loss=99.0,
            take_profit=102.0,
        )

    error = caught.value
    assert error.order_id == 'order-1'
    assert error.reference_id == 'reference-1'
    assert error.symbol == 'BTC'
    assert error.side == 'BUY'
    assert error.amount == 100.0
    assert isinstance(error.submitted_at, datetime)
    assert error.submitted_at.tzinfo == timezone.utc


def test_close_submission_returns_immediately_without_portfolio_polling(monkeypatch):
    client = ResilientEtoroClient(settings=settings())
    client.position_instruments['position-1'] = 100
    captured = {}

    def post(path, payload):
        captured['path'] = path
        captured['payload'] = payload
        return {
            'orderForClose': {
                'positionID': 'position-1',
                'instrumentID': 100,
                'orderID': 'close-order-1',
                'statusID': 1,
            },
            'referenceId': 'close-reference-1',
        }

    monkeypatch.setattr(client, '_post', post)
    monkeypatch.setattr(
        client,
        'get_portfolio',
        lambda: (_ for _ in ()).throw(
            AssertionError('portfolio polling is forbidden in close submission')
        ),
    )

    submission = client.close_position('position-1')

    assert submission.position_id == 'position-1'
    assert submission.close_order_id == 'close-order-1'
    assert submission.reference_id == 'close-reference-1'
    assert captured['payload'] == {'InstrumentId': 100, 'UnitsToDeduct': None}
    assert client.position_instruments['position-1'] == 100

    client.forget_position_instrument('position-1')
    assert 'position-1' not in client.position_instruments


def test_close_response_without_acceptance_is_submission_unknown(monkeypatch):
    client = ResilientEtoroClient(settings=settings())
    client.position_instruments['position-1'] = 100
    monkeypatch.setattr(
        client,
        '_post',
        lambda path, payload: {
            'orderForClose': {
                'positionID': 'position-1',
                'orderID': 'close-order-1',
                'statusID': 0,
            },
            'referenceId': 'close-reference-1',
        },
    )

    with pytest.raises(ClosePositionSubmissionUnknownError) as caught:
        client.close_position('position-1')

    assert caught.value.close_order_id == 'close-order-1'
    assert caught.value.reference_id == 'close-reference-1'
    assert client.position_instruments['position-1'] == 100


def test_close_business_rejection_is_not_treated_as_network_ambiguity(monkeypatch):
    client = ResilientEtoroClient(settings=settings())
    client.position_instruments['position-1'] = 100
    monkeypatch.setattr(
        client,
        '_post',
        lambda path, payload: {
            'status': {
                'name': 'Rejected',
                'errorCode': 42,
                'errorMessage': 'position cannot be closed',
            }
        },
    )

    with pytest.raises(ClosePositionRejectedError):
        client.close_position('position-1')

    assert client.position_instruments['position-1'] == 100


def test_close_network_timeout_is_submission_unknown(monkeypatch):
    client = ResilientEtoroClient(settings=settings())
    client.position_instruments['position-1'] = 100

    def timeout(path, payload):
        raise requests.Timeout('network timeout')

    monkeypatch.setattr(client, '_post', timeout)

    with pytest.raises(ClosePositionSubmissionUnknownError) as caught:
        client.close_position('position-1')

    assert isinstance(caught.value.cause, requests.Timeout)
    assert client.position_instruments['position-1'] == 100
