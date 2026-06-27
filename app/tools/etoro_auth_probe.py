import hashlib
import json
from dataclasses import dataclass
from uuid import uuid4

import requests

from app.config.settings import get_settings


@dataclass(frozen=True)
class ProbeEndpoint:
    name: str
    path: str
    params: dict | None = None


@dataclass(frozen=True)
class HeaderVariant:
    name: str
    headers: dict[str, str]


def main() -> None:
    settings = get_settings()
    base_url = settings.etoro_api_base_url.rstrip('/')

    print('=== eToro auth probe ===')
    print(f'base_url={base_url}')
    print(f'etoro_env={settings.etoro_env}')
    print(f'api_key={_fingerprint(settings.etoro_api_key)}')
    print(f'user_key={_fingerprint(settings.etoro_user_key)}')
    print()

    if not settings.etoro_api_key or not settings.etoro_user_key:
        print('ERROR: ETORO_API_KEY or ETORO_USER_KEY is empty.')
        return

    if _looks_wrapped(settings.etoro_api_key) or _looks_wrapped(settings.etoro_user_key):
        print('WARNING: one key appears to include wrapping quotes. Remove quotes from .env values.')
        print()

    if _has_surrounding_whitespace(settings.etoro_api_key) or _has_surrounding_whitespace(settings.etoro_user_key):
        print('WARNING: one key appears to include leading/trailing whitespace.')
        print()

    endpoints = [
        ProbeEndpoint(
            name='market_search_btc',
            path='/api/v1/market-data/search',
            params={'internalSymbolFull': 'BTC'},
        ),
        ProbeEndpoint(
            name='portfolio_env',
            path=f'/api/v1/trading/info/{settings.etoro_env}/portfolio',
        ),
        ProbeEndpoint(
            name='portfolio_demo_forced',
            path='/api/v1/trading/info/demo/portfolio',
        ),
    ]

    variants = _header_variants(
        api_key=settings.etoro_api_key.strip().strip('"\''),
        user_key=settings.etoro_user_key.strip().strip('"\''),
    )

    for endpoint in endpoints:
        print(f'--- endpoint: {endpoint.name} {endpoint.path} params={endpoint.params} ---')
        for variant in variants:
            _probe_endpoint(
                base_url=base_url,
                endpoint=endpoint,
                variant=variant,
            )
        print()


def _header_variants(api_key: str, user_key: str) -> list[HeaderVariant]:
    common = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    return [
        HeaderVariant(
            name='current_lowercase_x_headers',
            headers={
                **common,
                'x-request-id': str(uuid4()),
                'x-api-key': api_key,
                'x-user-key': user_key,
            },
        ),
        HeaderVariant(
            name='canonical_x_headers',
            headers={
                **common,
                'X-Request-ID': str(uuid4()),
                'X-API-KEY': api_key,
                'X-USER-KEY': user_key,
            },
        ),
        HeaderVariant(
            name='camel_x_headers',
            headers={
                **common,
                'X-Request-Id': str(uuid4()),
                'X-Api-Key': api_key,
                'X-User-Key': user_key,
            },
        ),
        HeaderVariant(
            name='bearer_api_plus_user_key',
            headers={
                **common,
                'x-request-id': str(uuid4()),
                'Authorization': f'Bearer {api_key}',
                'x-user-key': user_key,
            },
        ),
    ]


def _probe_endpoint(base_url: str, endpoint: ProbeEndpoint, variant: HeaderVariant) -> None:
    url = f'{base_url}/{endpoint.path.lstrip("/")}'

    try:
        response = requests.get(
            url,
            headers=variant.headers,
            params=endpoint.params,
            timeout=10,
        )
    except requests.RequestException as exc:
        print(f'{variant.name}: REQUEST_ERROR error={exc}')
        return

    body = _safe_body(response)
    print(
        f'{variant.name}: status={response.status_code} ok={response.ok} '
        f'content_type={response.headers.get("content-type", "")} body={body}'
    )


def _safe_body(response: requests.Response) -> str:
    text = response.text or ''
    try:
        payload = response.json()
        text = json.dumps(payload, ensure_ascii=False)
    except ValueError:
        pass

    text = text.replace('\n', ' ').replace('\r', ' ')
    if len(text) > 500:
        return f'{text[:500]}...'

    return text


def _fingerprint(value: str) -> str:
    if value is None:
        return '<none>'

    digest = hashlib.sha256(value.encode('utf-8')).hexdigest()[:10]
    clean_value = value.strip()
    prefix = clean_value[:4] if len(clean_value) >= 4 else clean_value
    suffix = clean_value[-4:] if len(clean_value) >= 4 else clean_value
    return f'len={len(value)} stripped_len={len(clean_value)} prefix={prefix!r} suffix={suffix!r} sha256_10={digest}'


def _looks_wrapped(value: str) -> bool:
    stripped = value.strip()
    return len(stripped) >= 2 and stripped[0] in ('"', "'") and stripped[-1] == stripped[0]


def _has_surrounding_whitespace(value: str) -> bool:
    return value != value.strip()


if __name__ == '__main__':
    main()
