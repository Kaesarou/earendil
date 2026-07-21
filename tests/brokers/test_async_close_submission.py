from datetime import datetime

import pytest
import requests

from app.brokers.base import (
    ClosePositionRejectedError,
    ClosePositionSubmissionUnknownError,
)
from app.brokers.etoro.resilient_client import ResilientEtoroClient
from app.config.settings import Settings


def client():
    result = ResilientEtoroClient(
        Settings(
            BROKER='etoro_demo',
            ETORO_API_KEY='api-key',
            ETORO_USER_KEY='user-key',
        )
    )
    result.position_instruments['9001'] = 100000
    return result


def test_close_returns_immediately_after_accepted_post_without_polling(monkeypatch):
    broker = client()
    calls = []
    monkeypatch.setattr(
        broker,
        '_post',
        lambda path, payload: calls.append((path, payload)) or {
            'orderForClose': {
                'positionID': 9001,
                'instrumentID': 100000,
                'orderID': 362447424,
                'statusID': 1,
            },
            'referenceId': 'ref-close-1',
        },
    )
    monkeypatch.setattr(
        broker,
        '_wait_for_executed_order',
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError('order polling is forbidden for closes')
        ),
    )

    submission = broker.close_position('9001')

    assert len(calls) == 1
    assert submission.position_id == '9001'
    assert submission.close_order_id == '362447424'
    assert submission.reference_id == 'ref-close-1'
    assert isinstance(submission.submitted_at, datetime)
    assert isinstance(submission.accepted_at, datetime)
    assert '9001' in broker.position_instruments


def test_close_timeout_is_submission_unknown(monkeypatch):
    broker = client()
    monkeypatch.setattr(
        broker,
        '_post',
        lambda path, payload: (_ for _ in ()).throw(
            requests.Timeout('network timeout')
        ),
    )

    with pytest.raises(ClosePositionSubmissionUnknownError):
        broker.close_position('9001')


def test_explicit_client_error_is_rejected(monkeypatch):
    broker = client()
    response = requests.Response()
    response.status_code = 422
    error = requests.HTTPError('unprocessable close', response=response)
    monkeypatch.setattr(
        broker,
        '_post',
        lambda path, payload: (_ for _ in ()).throw(error),
    )

    with pytest.raises(ClosePositionRejectedError):
        broker.close_position('9001')


def test_retryable_http_error_remains_submission_unknown(monkeypatch):
    broker = client()
    response = requests.Response()
    response.status_code = 429
    error = requests.HTTPError('rate limited', response=response)
    monkeypatch.setattr(
        broker,
        '_post',
        lambda path, payload: (_ for _ in ()).throw(error),
    )

    with pytest.raises(ClosePositionSubmissionUnknownError):
        broker.close_position('9001')
