import pytest

from app.brokers.etoro.etoro_client import EtoroClient
from app.config.settings import Settings


def build_client(base_currency: str = 'USD') -> EtoroClient:
    return EtoroClient(
        settings=Settings(
            BROKER='etoro_demo',
            BASE_CURRENCY=base_currency,
            ETORO_API_KEY='api-key',
            ETORO_USER_KEY='user-key',
        ),
    )


def test_etoro_buy_open_order_payload_uses_market_buy_without_protection_rates():
    client = build_client(base_currency='EUR')

    payload = client._build_open_order_payload(
        instrument_id=1234,
        side='BUY',
        amount=500.0,
        stop_loss=99.0,
        take_profit=101.0,
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


def test_etoro_sell_open_order_payload_uses_short_cfd_and_stop_loss_rate():
    client = build_client(base_currency='USD')

    payload = client._build_open_order_payload(
        instrument_id=1261,
        side='SELL',
        amount=497.26,
        stop_loss=337.4092,
        take_profit=334.8862,
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
        'StopLossRate': 337.4092,
    }


def test_etoro_open_order_payload_currently_does_not_send_take_profit_rate():
    client = build_client()

    payload = client._build_open_order_payload(
        instrument_id=1261,
        side='SELL',
        amount=497.26,
        stop_loss=337.4092,
        take_profit=334.8862,
    )

    assert 'TakeProfitRate' not in payload
    assert 'takeProfitRate' not in payload
    assert 'take_profit' not in payload


@pytest.mark.parametrize(
    ('side', 'transaction'),
    [
        ('BUY', 'buy'),
        ('SELL', 'sellShort'),
    ],
)
def test_etoro_open_transaction_for_supported_sides(side: str, transaction: str):
    client = build_client()

    assert client._open_transaction_for_side(side) == transaction


def test_etoro_open_transaction_rejects_unsupported_side():
    client = build_client()

    with pytest.raises(ValueError, match='Unsupported side for eToro transaction'):
        client._open_transaction_for_side('HOLD')
