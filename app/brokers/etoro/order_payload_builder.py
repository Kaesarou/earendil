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

    return payload


def open_transaction_for_side(side: str) -> str:
    if side == 'BUY':
        return 'buy'

    if side == 'SELL':
        return 'sellShort'

    raise ValueError(f'Unsupported side for eToro transaction: {side}')


def leverage_for_side(side: str) -> int:
    return 1
