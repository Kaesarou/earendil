import time
from datetime import datetime
from typing import Any

import requests

from app.brokers.etoro.endpoint_paths import instrument_rates_path
from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.http_url_builder import build_http_url
from app.brokers.etoro.request_settings import default_request_timeout_seconds
from app.config.settings import Settings
from app.market_data_probe.historical_candles import (
    historical_candles_path,
    normalize_historical_candles,
)
from app.market_data_probe.metrics import StudyMetrics
from app.market_data_probe.models import NormalizedRate, utc_now
from app.market_data_probe.recorder import ProbeRecorder
from app.market_data_probe.websocket_protocol import normalize_rate_payload


class EtoroRestProbe:
    def __init__(
        self,
        *,
        settings: Settings,
        recorder: ProbeRecorder,
        metrics: StudyMetrics,
    ):
        if settings.broker.strip().lower() != 'etoro_demo':
            raise ValueError(
                'Market-data probes require BROKER=etoro_demo. '
                'Real-account mode is intentionally unsupported.'
            )
        if not settings.etoro_api_key or not settings.etoro_user_key:
            raise ValueError(
                'ETORO_API_KEY and ETORO_USER_KEY are required.'
            )
        self.client = EtoroClient(settings)
        self.recorder = recorder
        self.metrics = metrics

    def resolve_symbols(self, symbols: list[str]) -> dict[str, int]:
        result: dict[str, int] = {}
        for symbol in symbols:
            started = time.perf_counter()
            succeeded = False
            try:
                instrument_id = self.client._find_instrument_id(symbol)
                succeeded = True
            finally:
                self.metrics.add_request(
                    'instrument_search',
                    duration_ms=(time.perf_counter() - started) * 1000,
                    succeeded=succeeded,
                )
            result[symbol] = instrument_id
            self.recorder.append(
                'events',
                {
                    'event': 'instrument_resolved',
                    'symbol': symbol,
                    'instrument_id': instrument_id,
                    'observed_at': utc_now(),
                },
            )
        return result

    def fetch_rates(
        self,
        *,
        group_name: str,
        symbols: list[str],
        instrument_id_by_symbol: dict[str, int],
    ) -> list[NormalizedRate]:
        instrument_ids = [instrument_id_by_symbol[symbol] for symbol in symbols]
        observed_at = utc_now()
        payload = self._get_json(
            instrument_rates_path(instrument_ids),
            category='rest_rates',
            raw_stream='raw_rest_rates',
            metadata={'group': group_name, 'symbols': symbols},
        )
        result: list[NormalizedRate] = []
        raw_rates = payload.get('rates')
        if not isinstance(raw_rates, list):
            raise ValueError('eToro rates response does not contain rates list.')
        symbol_by_instrument_id = {
            instrument_id: symbol
            for symbol, instrument_id in instrument_id_by_symbol.items()
        }
        for raw_rate in raw_rates:
            if not isinstance(raw_rate, dict):
                continue
            instrument_id = _instrument_id(raw_rate)
            if instrument_id is None:
                continue
            symbol = symbol_by_instrument_id.get(instrument_id)
            if symbol is None:
                continue
            normalized = normalize_rate_payload(
                raw_rate,
                source='rest_rate',
                symbol=symbol,
                instrument_id=instrument_id,
                received_at=observed_at,
            )
            if normalized is None:
                continue
            result.append(normalized)
            self.metrics.add_rate(normalized)
            self.recorder.append('normalized_rates', normalized.to_dict())
        return result

    def fetch_historical_candles(
        self,
        *,
        symbol: str,
        instrument_id: int,
        candle_count: int = 30,
    ) -> None:
        observed_at = utc_now()
        path = historical_candles_path(
            instrument_id=instrument_id,
            direction='desc',
            interval='OneMinute',
            candle_count=candle_count,
        )
        payload = self._get_json(
            path,
            category='rest_candles',
            raw_stream='raw_rest_candles',
            metadata={
                'symbol': symbol,
                'instrument_id': instrument_id,
                'interval': 'OneMinute',
                'direction': 'desc',
                'candle_count': candle_count,
            },
        )
        for candle in normalize_historical_candles(
            payload,
            symbol=symbol,
            instrument_id=instrument_id,
            observed_at=observed_at,
        ):
            self.metrics.add_historical_candle(candle)
            self.recorder.append('normalized_candles', candle.to_dict())

    def _get_json(
        self,
        path: str,
        *,
        category: str,
        raw_stream: str,
        metadata: dict[str, Any],
    ) -> dict:
        url = build_http_url(self.client.etoro_api_base_url, path)
        started = time.perf_counter()
        succeeded = False
        response = None
        error: Exception | None = None
        try:
            response = requests.get(
                url,
                headers=self.client.headers,
                timeout=default_request_timeout_seconds(),
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError('Expected a JSON object from eToro REST API.')
            succeeded = True
            return payload
        except Exception as exc:
            error = exc
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            self.metrics.add_request(
                category,
                duration_ms=duration_ms,
                succeeded=succeeded,
            )
            self.recorder.append(
                raw_stream,
                {
                    **metadata,
                    'requested_at': datetime.now().astimezone(),
                    'duration_ms': round(duration_ms, 3),
                    'status_code': (
                        response.status_code if response is not None else None
                    ),
                    'response_headers': (
                        _diagnostic_headers(response.headers)
                        if response is not None
                        else {}
                    ),
                    'payload': (
                        _safe_response_payload(response)
                        if response is not None
                        else None
                    ),
                    'error': str(error) if error is not None else None,
                },
            )


def _instrument_id(payload: dict) -> int | None:
    value = payload.get('instrumentID', payload.get('instrumentId'))
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _diagnostic_headers(headers) -> dict[str, str]:
    allowed = {
        'date',
        'retry-after',
        'x-request-id',
        'x-ratelimit-limit',
        'x-ratelimit-remaining',
        'x-ratelimit-reset',
        'ratelimit-limit',
        'ratelimit-remaining',
        'ratelimit-reset',
    }
    return {
        str(key): str(value)
        for key, value in headers.items()
        if str(key).lower() in allowed
    }


def _safe_response_payload(response) -> object:
    try:
        return response.json()
    except (requests.RequestException, ValueError):
        return {'non_json_body': response.text[:2000]}
