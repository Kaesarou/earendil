def extract_open_positions(payload: dict) -> list[dict]:
    client_portfolio = payload.get('clientPortfolio')
    if isinstance(client_portfolio, dict):
        positions = client_portfolio.get('positions')
        if isinstance(positions, list):
            return [position for position in positions if isinstance(position, dict)]

    positions = payload.get('positions')
    if isinstance(positions, list):
        return [position for position in positions if isinstance(position, dict)]

    data = payload.get('data')
    if isinstance(data, dict):
        return extract_open_positions(data)

    return []


def contains_open_position(payload: dict, position_id: str) -> bool:
    open_positions = extract_open_positions(payload)

    for position in open_positions:
        candidate_position_id = (
            position.get('positionID')
            or position.get('positionId')
            or position.get('PositionID')
            or position.get('PositionId')
        )

        if str(candidate_position_id) != str(position_id):
            continue

        is_open = position.get('isOpen')
        if is_open is False:
            return False

        return True

    return False
