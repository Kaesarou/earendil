def extract_optional_float(payload: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return float(value)

    return None


def extract_float(payload: dict, keys: tuple[str, ...]) -> float:
    value = extract_optional_float(payload, keys)

    if value is None:
        raise ValueError(f'Unable to extract required float keys={keys}. Payload={payload}')

    return value


def extract_optional_int(payload: dict, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return int(value)

    return None


def extract_int(payload: dict, keys: tuple[str, ...]) -> int:
    value = extract_optional_int(payload, keys)

    if value is None:
        raise ValueError(f'Unable to extract required int keys={keys}. Payload={payload}')

    return value
