def extract_items(payload: dict) -> list[dict]:
    for key in ('items', 'data', 'Data', 'Items', 'instruments', 'rates'):
        value = payload.get(key)

        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

        if isinstance(value, dict):
            return [value]

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    return []


def resolve_exact_instrument_id(symbol: str, payload: dict) -> int:
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
    instrument_id = (
        instrument.get('internalInstrumentId')
        or instrument.get('instrumentId')
        or instrument.get('InstrumentID')
        or instrument.get('instrumentID')
        or instrument.get('id')
    )

    if instrument_id is None:
        return None

    return int(instrument_id)


def candidate_summaries(items: list[dict]) -> list[dict]:
    return [
        {
            'internalSymbolFull': item.get('internalSymbolFull'),
            'displayName': item.get('internalInstrumentDisplayName'),
            'instrumentId': item.get('internalInstrumentId') or item.get('instrumentId'),
            'currentRate': item.get('currentRate'),
        }
        for item in items[:10]
    ]
