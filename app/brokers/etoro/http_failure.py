def is_http_success(response) -> bool:
    return bool(response.ok)


def raise_for_failed_response(response) -> None:
    if is_http_success(response):
        return

    response.raise_for_status()
