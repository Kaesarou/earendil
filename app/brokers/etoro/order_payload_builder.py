def build_open_order_payload(
    *,
    instrument_id: int,
    side: str,
    amount: float,
    stop_loss: float,
    take_profit: float,
    order_currency: str,
    sellshort_safety_sl_buffer_percent: float = 0.30,
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
            buffer_percent=sellshort_safety_sl_buffer_percent,
        )

    return payload


def calculate_sellshort_safety_stop_loss(*, bot_stop_loss: float, buffer_percent: float) -> float:
    if bot_stop_loss is None or bot_stop_loss <= 0:
        raise ValueError(f'Invalid bot_stop_loss for eToro sellShort safety stop: {bot_stop_loss}')
    if buffer_percent <= 0:
        raise ValueError(f'eToro sellShort safety stop buffer must be positive: {buffer_percent}')
    return round(bot_stop_loss * (1 + buffer_percent / 100), 5)


def open_transaction_for_side(side: str) -> str:
    if side == 'BUY':
        return 'buy'

    if side == 'SELL':
        return 'sellShort'

    raise ValueError(f'Unsupported side for eToro transaction: {side}')


def leverage_for_side(side: str) -> int:
    return 1
