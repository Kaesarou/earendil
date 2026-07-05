from app.brokers.etoro.scalar_extractors import (
    extract_float,
    extract_int,
    extract_optional_float,
)
from app.market.models import MarketSnapshot


def to_market_snapshot(
    *,
    symbol: str,
    rates_payload: dict,
    symbol_by_instrument_id: dict[int, str],
) -> MarketSnapshot:
    return to_market_snapshots(
        rates_payload=rates_payload,
        symbol_by_instrument_id=symbol_by_instrument_id,
    )[symbol]


def to_market_snapshots(
    *,
    rates_payload: dict,
    symbol_by_instrument_id: dict[int, str],
) -> dict[str, MarketSnapshot]:
    result: dict[str, MarketSnapshot] = {}
    rates = rates_payload['rates']

    for rate in rates:
        instrument_id = extract_int(rate, ('instrumentID', 'instrumentId'))

        symbol = symbol_by_instrument_id.get(instrument_id)
        if symbol is None:
            raise ValueError(f'Unable to find cached symbol by instrument_id={instrument_id}.')

        bid = extract_float(rate, ('Bid', 'bid', 'bidPrice'))
        ask = extract_float(rate, ('Ask', 'ask', 'askPrice'))

        last = extract_optional_float(
            rate,
            ('Last', 'last', 'lastPrice', 'Price', 'price', 'lastExecution'),
        )

        if last is None:
            last = (bid + ask) / 2

        result[symbol] = MarketSnapshot.now(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
        )

    return result
