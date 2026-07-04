def remember_position_instrument_id(
    *,
    position_instruments: dict[str, int],
    position_id: str,
    instrument_id: int,
) -> None:
    position_instruments[position_id] = instrument_id


def cached_position_instrument_id(
    *,
    position_instruments: dict[str, int],
    position_id: str,
) -> int | None:
    return position_instruments.get(position_id)


def forget_position_instrument_id(
    *,
    position_instruments: dict[str, int],
    position_id: str,
) -> None:
    position_instruments.pop(position_id, None)


def require_position_instrument_id(
    *,
    position_instruments: dict[str, int],
    position_id: str,
) -> int:
    instrument_id = cached_position_instrument_id(
        position_instruments=position_instruments,
        position_id=position_id,
    )

    if instrument_id is None:
        raise ValueError(
            f'Cannot close eToro position without known instrument id: {position_id}'
        )

    return instrument_id
