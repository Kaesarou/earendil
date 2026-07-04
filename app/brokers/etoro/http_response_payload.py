def response_payload(response) -> dict:
    if not response.content:
        return {}

    return response.json()
