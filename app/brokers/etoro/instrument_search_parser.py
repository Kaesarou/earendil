from app.brokers.etoro.payload_collections import keep_dict_items
from app.brokers.etoro.scalar_extractors import extract_optional_int
from app.brokers.etoro.string_extractors import extract_optional_string


INSTRUMENT_ITEMS_KEYS = ('items', 'data', 'Data', 'Items', 'instruments', 'rates')
INSTRUMENT_SYMBOL_KEYS = ('internalSymbolFull',)
INSTRUMENT_DISPLAY_NAME_KEY = 'internalInstrumentDisplayName'
INSTRUMENT_CURRENT_RATE_KEY = 'currentRate'
INSTRUMENT_ID_KEYS = (
    'internalInstrumentId',
    'instrumentId',
    'InstrumentID',
    'instrumentID',
    'id',
)


def normalize_symbol(symbol: str) -> str:
    return symbol.upper()


def extract_items(payload: dict | list) -> list[dict]:
    if isinstance(payload, list):
        return keep_dict_items(payload)

    for key in INSTRUMENT_ITEMS_KEYS:
        value = payload.get(key)

        if isinstance(value, list):
            return keep_dict_items(value)

        if isinstance(value, dict):
            return [value]

    return []


def extract_instrument_symbol(instrument: dict) -> str | None:
    return extract_optional_string(instrument, INSTRUMENT_SYMBOL_KEYS)


def resolve_exact_instrument_id(symbol: str, payload: dict | list) -> int:
    normalized_symbol = normalize_symbol(symbol)
    items = extract_items(payload)

    exact_matches = [
        item for item in items
        if normalize_symbol(extract_instrument_symbol(item) or '') == normalized_symbol
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
            'internalSymbolFull': extract_instrument_symbol(item),
            'displayName': item.get(INSTRUMENT_DISPLAY_NAME_KEY),
            'instrumentId': extract_instrument_id(item),
            'currentRate': item.get(INSTRUMENT_CURRENT_RATE_KEY),
        }
        for item in items[:10]
    ]
