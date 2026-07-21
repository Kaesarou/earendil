SELLSHORT_SAFETY_SL_BUFFER_PERCENT = 0.30


def build_open_order_payload(
    *,
    instrument_id: int,
    side: str,
    amount: float,
    stop_loss: float,
    take_profit: float,
    order_currency: str,
) -> dict:
    transaction = open_transaction_for_side(side)

    payload = {
        'action': 'open',
        'transaction': transaction,
        'InstrumentID': instrument_id,
        'orderType': 'mkt',
        'leverage': leverage_for_side(side),
        'amount': amount,
        'orderCurrency': order_currency.lower(),
    }

    if side == 'SELL':
        payload['settlementType'] = 'cfd'
        payload['StopLossRate'] = calculate_sellshort_safety_stop_loss(
            bot_stop_loss=stop_loss,
        )

    return payload


def calculate_sellshort_safety_stop_loss(*, bot_stop_loss: float) -> float:
    if bot_stop_loss is None or bot_stop_loss <= 0:
        raise ValueError(
            f'Invalid bot_stop_loss for eToro sellShort safety stop: '
            f'{bot_stop_loss}'
        )
    return round(
        bot_stop_loss * (1 + SELLSHORT_SAFETY_SL_BUFFER_PERCENT / 100),
        5,
    )


def open_transaction_for_side(side: str) -> str:
    if side == 'BUY':
        return 'buy'

    if side == 'SELL':
        return 'sellShort'

    raise ValueError(f'Unsupported side for eToro transaction: {side}')


def leverage_for_side(side: str) -> int:
    return 1
