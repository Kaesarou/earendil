def normalized_symbol(symbol: str) -> str:
    return symbol.upper()


def cached_instrument_id(
    *,
    instrument_ids_by_symbol: dict[str, int],
    symbol: str,
) -> int | None:
    return instrument_ids_by_symbol.get(normalized_symbol(symbol))


def remember_instrument_id(
    *,
    instrument_ids_by_symbol: dict[str, int],
    symbol_by_instrument_id: dict[int, str],
    symbol: str,
    instrument_id: int,
) -> None:
    normalized = normalized_symbol(symbol)
    instrument_ids_by_symbol[normalized] = instrument_id
    symbol_by_instrument_id[instrument_id] = normalized
