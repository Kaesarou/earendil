def normalize_side(side: str) -> str:
    return side.strip().upper()


def ensure_side_is_allowed(side: str) -> None:
    if side == 'BUY':
        return

    if side == 'SELL':
        return

    raise ValueError(f'Unsupported side for eToro order: {side}')


def normalize_and_validate_side(side: str) -> str:
    normalized_side = normalize_side(side)
    ensure_side_is_allowed(normalized_side)
    return normalized_side
