def build_headers(*, request_id: str, api_key: str, user_key: str) -> dict[str, str]:
    return {
        'x-request-id': request_id,
        'x-api-key': api_key,
        'x-user-key': user_key,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
