def build_etoro_url(*, base_url: str, path: str) -> str:
    return f'{base_url.rstrip("/")}/{path.lstrip("/")}'
