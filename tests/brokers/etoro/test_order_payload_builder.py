import pytest

from app.brokers.etoro.order_payload_builder import (
    build_open_order_payload,
    open_transaction_for_side,
)

BROKER_EXIT_FIELDS = (
    'StopLossRate',
    'TakeProfitRate',
    'stopLossRate',
    'takeProfitRate',
    'stopLossType',
)


def assert_no_broker_side_exit_fields(payload: dict) -> None:
    for field in BROKER_EXIT_FIELDS:
        assert field not in payload


def test_etoro_buy_open_order_payload_uses_market_buy_without_broker_side_exits():
    payload = build_open_order_payload(
        instrument_id=1234,
        side='BUY',
        amount=500.0,
        stop_loss=99.0,
        take_profit=101.0,
        order_currency='EUR',
    )

    assert payload == {
        'action': 'open',
        'transaction': 'buy',
        'InstrumentID': 1234,
        'orderType': 'mkt',
        'leverage': 1,
        'amount': 500.0,
        'orderCurrency': 'eur',
    }
    assert_no_broker_side_exit_fields(payload)


def test_etoro_sell_open_order_payload_uses_short_cfd_without_broker_side_exits():
    payload = build_open_order_payload(
        instrument_id=1261,
        side='SELL',
        amount=497.26,
        stop_loss=337.4092,
        take_profit=334.8862,
        order_currency='USD',
    )

    assert payload == {
        'action': 'open',
        'transaction': 'sellShort',
        'InstrumentID': 1261,
        'orderType': 'mkt',
        'leverage': 1,
        'amount': 497.26,
        'orderCurrency': 'usd',
        'settlementType': 'cfd',
    }
    assert_no_broker_side_exit_fields(payload)


@pytest.mark.parametrize(
    ('side', 'transaction'),
    [
        ('BUY', 'buy'),
        ('SELL', 'sellShort'),
    ],
)
def test_etoro_open_transaction_for_supported_sides(side: str, transaction: str):
    assert open_transaction_for_side(side) == transaction


def test_etoro_open_transaction_rejects_unsupported_side():
    with pytest.raises(ValueError, match='Unsupported side for eToro transaction'):
        open_transaction_for_side('HOLD')
