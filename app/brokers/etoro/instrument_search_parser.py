from app.brokers.etoro.payload_collections import keep_dict_items
from app.brokers.etoro.scalar_extractors import extract_optional_int


INSTRUMENT_ID_KEYS = (
    'internalInstrumentId',
    'instrumentId',
    'InstrumentID',
    'instrumentID',
    'id',
)


def extract_items(payload: dict | list) -> list[dict]:
    if isinstance(payload, list):
        return keep_dict_items(payload)

    for key in ('items', 'data', 'Data', 'Items', 'instruments', 'rates'):
        value = payload.get(key)

        if isinstance(value, list):
            return keep_dict_items(value)

        if isinstance(value, dict):
            return [value]

    return []


def resolve_exact_instrument_id(symbol: str, payload: dict | list) -> int:
    normalized_symbol = symbol.upper()
    items = extract_items(payload)

    exact_matches = [
        item for item in items
        if str(item.get('internalSymbolFull', '')).upper() == normalized_symbol
    ]

    if not exact_matches:
        candidates = candidate_summaries(items)

        raise ValueError(
            f'No exact eToro instrument match found for symbol={symbol}. '
            f'Candidates={candidates}'
        )

    instrument = exact_matches[0]
    instrument_id = extract_instrument_id(instrument)

    if instrument_id is None:
        raise ValueError(
            f'Unable to find instrument id for symbol={symbol}. Instrument={instrument}'
        )

    return int(instrument_id)


def extract_instrument_id(instrument: dict) -> int | None:
    return extract_optional_int(instrument, INSTRUMENT_ID_KEYS)


def candidate_summaries(items: list[dict]) -> list[dict]:
    return [
        {
            'internalSymbolFull': item.get('internalSymbolFull'),
            'displayName': item.get('internalInstrumentDisplayName'),
            'instrumentId': extract_instrument_id(item),
            'currentRate': item.get('currentRate'),
        }
        for item in items[:10]
    ]
