from datetime import datetime, timezone

import pytest

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
