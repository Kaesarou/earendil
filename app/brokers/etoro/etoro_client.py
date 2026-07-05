import logging
import time
from uuid import uuid4

import requests

from app.brokers.base import BrokerClient
from app.brokers.etoro.account_equity_mapper import (
    extract_account_equity,
    extract_optional_account_equity,
)
from app.brokers.etoro.attempt_delay import delay_seconds_for_attempt
from app.brokers.etoro.broker_environment import broker_environment_from_name
from app.brokers.etoro.close_order_payload_builder import build_close_order_payload
from app.brokers.etoro.endpoint_paths import (
    close_position_path,
    demo_order_details_path,
    demo_portfolio_path,
    instrument_rates_path,
    instrument_search_path,
    open_order_path,
    real_order_lookup_path,
    real_portfolio_path,
)
from app.brokers.etoro.http_failure import raise_for_failed_response
from app.brokers.etoro.http_headers_builder import build_headers
from app.brokers.etoro.http_response_payload import response_payload
from app.brokers.etoro.http_retry_policy import (
    default_get_max_attempts,
    is_retryable_http_status,
)
from app.brokers.etoro.http_url_builder import build_http_url
from app.brokers.etoro.instrument_cache import (
    cached_instrument_id,
    remember_instrument_id,
)
from app.brokers.etoro.instrument_search_parser import (
    extract_items,
    resolve_exact_instrument_id,
)
from app.brokers.etoro.market_data_mapper import to_market_snapshots
from app.brokers.etoro.order_payload_builder import (
    build_open_order_payload,
    leverage_for_side,
    open_transaction_for_side,
)
from app.brokers.etoro.order_response_parser import (
    extract_order_error_code,
    extract_order_error_message,
    extract_order_id,
    extract_position_id_from_order_details,
    extract_reference_id,
    is_close_response_accepted,
    is_order_executed,
    is_order_rejected,
)
from app.brokers.etoro.portfolio_position_parser import (
    contains_open_position,
    extract_open_positions,
)
from app.brokers.etoro.position_instrument_cache import (
    forget_position_instrument_id,
    remember_position_instrument_id,
    require_position_instrument_id,
)
from app.brokers.etoro.scalar_extractors import (
    extract_float,
    extract_int,
    extract_optional_float,
    extract_optional_int,
)
from app.brokers.etoro.trade_side import (
    ensure_side_is_allowed,
    normalize_side,
)
from app.config.settings import Settings
from app.market.models import MarketSnapshot

logger = logging.getLogger(__name__)


class EtoroClient(BrokerClient):
    settings: Settings
    env: str
    position_instruments: dict[str, int]
    instrument_ids_by_symbol: dict[str, int]
    symbol_by_instrument_id: dict[int, str]
    etoro_api_base_url = 'https://public-api.etoro.com'

    def __init__(self, settings: Settings):
        self.settings = settings
        self.env = broker_environment_from_name(settings.broker)
        self.position_instruments: dict[str, int] = {}
        self.instrument_ids_by_symbol: dict[str, int] = {}
        self.symbol_by_instrument_id: dict[int, str] = {}

    # -------------------------------------------------------------------------
    # Public broker API
    # -------------------------------------------------------------------------

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        instrument_id = self._find_instrument_id(symbol)
        rates_payload = self._get_market_rates([instrument_id])

        return self._to_market_snapshot(
            symbol,
            rates_payload=rates_payload,
        )

    # Pour l'instant on est limité à 100 symbols
    def get_market_snapshots(self, symbols: list[str]) -> dict[str, MarketSnapshot]:
        instruments_ids = self._find_instruments_ids(symbols)
        rates_payload = self._get_market_rates(instruments_ids)

        return self._to_market_snapshots(
            rates_payload=rates_payload,
        )

    def get_account_equity(self) -> float:
        portfolio = self.get_portfolio()
        equity = self._extract_account_equity(portfolio)

        logger.info(
            'Account equity resolved | env=%s | equity=%s',
            self.env,
            equity,
        )

        return equity

    def open_position(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_loss: float,
        take_profit: float,
    ) -> str:
        normalized_side = self._normalize_side(side)
        self._ensure_side_is_allowed(normalized_side)

        instrument_id = self._find_instrument_id(symbol)
        payload = self._build_open_order_payload(
            instrument_id=instrument_id,
            side=normalized_side,
            amount=amount,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        logger.warning(
            'Sending eToro order | env=%s | symbol=%s | side=%s | transaction=%s | instrument_id=%s | amount=%s | stop_loss=%s | take_profit=%s | leverage=%s',
            self.env,
            symbol,
            normalized_side,
            payload.get('transaction'),
            instrument_id,
            amount,
            stop_loss,
            take_profit,
            payload.get('leverage'),
        )

        order_response = self._post(self._open_order_path(), payload)
        logger.info('eToro order response: %s', order_response)

        order_id = self._extract_order_id(order_response)
        reference_id = self._extract_reference_id(order_response)

        logger.info(
            'eToro order submitted | order_id=%s | reference_id=%s',
            order_id,
            reference_id,
        )

        order_details = self._wait_for_executed_order(order_id)
        position_id = self._extract_position_id_from_order_details(order_details)

        if position_id is None:
            raise RuntimeError(
                f'eToro order executed but no position id was found: '
                f'order_id={order_id}, details={order_details}'
            )

        remember_position_instrument_id(
            position_instruments=self.position_instruments,
            position_id=position_id,
            instrument_id=instrument_id,
        )

        logger.info(
            'eToro position confirmed | order_id=%s | position_id=%s | instrument_id=%s | side=%s',
            order_id,
            position_id,
            instrument_id,
            normalized_side,
        )

        return position_id

    def close_position(self, position_id: str) -> None:
        instrument_id = require_position_instrument_id(
            position_instruments=self.position_instruments,
            position_id=position_id,
        )
        payload = build_close_order_payload(instrument_id)

        close_response = self._post(
            self._close_position_path(position_id),
            payload,
        )

        logger.info('eToro close position response: %s', close_response)

        close_order_id = self._extract_order_id(close_response)

        if self._is_close_response_accepted(close_response, position_id):
            self._wait_until_position_closed(position_id)

            logger.info(
                'eToro close confirmed by portfolio | position_id=%s | close_order_id=%s | response=%s',
                position_id,
                close_order_id,
                close_response,
            )

            forget_position_instrument_id(
                position_instruments=self.position_instruments,
                position_id=position_id,
            )
            return

        close_details = self._wait_for_executed_order(close_order_id)
        self._wait_until_position_closed(position_id)

        logger.info(
            'eToro close confirmed | position_id=%s | close_order_id=%s | details=%s',
            position_id,
            close_order_id,
            close_details,
        )

        forget_position_instrument_id(
            position_instruments=self.position_instruments,
            position_id=position_id,
        )

    def get_order_details(self, order_id: str) -> dict:
        if self.env == 'demo':
            return self._get(self._demo_order_details_path(order_id))

        return self._get(
            self._real_order_lookup_path(),
            params={'orderId': order_id},
        )

    def get_portfolio(self) -> dict:
        if self.env == 'demo':
            return self._get(self._demo_portfolio_path())

        return self._get(self._real_portfolio_path())

    def is_position_open(self, position_id: str) -> bool:
        portfolio = self.get_portfolio()
        return self._contains_open_position(portfolio, position_id)

    def remember_position_instrument(self, position_id: str, symbol: str) -> None:
        instrument_id = self._find_instrument_id(symbol)
        remember_position_instrument_id(
            position_instruments=self.position_instruments,
            position_id=position_id,
            instrument_id=instrument_id,
        )

        logger.info(
            'eToro restored position instrument | position_id=%s | symbol=%s | instrument_id=%s',
            position_id,
            symbol,
            instrument_id,
        )

    # -------------------------------------------------------------------------
    # HTTP helpers
    # -------------------------------------------------------------------------

    @property
    def headers(self) -> dict[str, str]:
        return build_headers(
            request_id=str(uuid4()),
            api_key=self.settings.etoro_api_key,
            user_key=self.settings.etoro_user_key,
        )

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = build_http_url(self.etoro_api_base_url, path)
        max_attempts = default_get_max_attempts()

        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=default_request_timeout_seconds(),
                )
            except requests.Timeout as exc:
                logger.warning(
                    'eToro GET timeout | attempt=%s/%s | url=%s | params=%s | error=%s',
                    attempt,
                    max_attempts,
                    url,
                    params,
                    exc,
                )

                if attempt == max_attempts:
                    raise

                time.sleep(delay_seconds_for_attempt(attempt))
                continue

            except requests.RequestException as exc:
                logger.warning(
                    'eToro GET request failed | attempt=%s/%s | url=%s | params=%s | error=%s',
                    attempt,
                    max_attempts,
                    url,
                    params,
                    exc,
                )

                if attempt == max_attempts:
                    raise

                time.sleep(delay_seconds_for_attempt(attempt))
                continue

            if is_retryable_http_status(response.status_code) and attempt < max_attempts:
                logger.warning(
                    'eToro GET retryable error | attempt=%s/%s | status=%s | url=%s | params=%s | response=%s',
                    attempt,
                    max_attempts,
                    response.status_code,
                    url,
                    params,
                    response.text,
                )

                time.sleep(delay_seconds_for_attempt(attempt))
                continue

            if not response.ok:
                logger.error(
                    'eToro GET failed | status=%s | url=%s | params=%s | response=%s',
                    response.status_code,
                    url,
                    params,
                    response.text,
                )
                raise_for_failed_response(response)

            return response_payload(response)

        raise RuntimeError(f'eToro GET failed after retries | url={url} | params={params}')

    def _post(self, path: str, payload: dict) -> dict:
        url = build_http_url(self.etoro_api_base_url, path)

        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=default_request_timeout_seconds(),
            )
        except requests.Timeout as exc:
            logger.error(
                'eToro POST timeout | url=%s | payload=%s | error=%s',
                url,
                payload,
                exc,
            )
            raise

        except requests.RequestException as exc:
            logger.error(
                'eToro POST request failed | url=%s | payload=%s | error=%s',
                url,
                payload,
                exc,
            )
            raise

        if not response.ok:
            logger.error(
                'eToro POST failed | status=%s | url=%s | payload=%s | response=%s',
                response.status_code,
                url,
                payload,
                response.text,
            )
            raise_for_failed_response(response)

        return response_payload(response)

    # -------------------------------------------------------------------------
    # Safety guards
    # -------------------------------------------------------------------------

    def _normalize_side(self, side: str) -> str:
        return normalize_side(side)

    def _ensure_side_is_allowed(self, side: str) -> None:
        ensure_side_is_allowed(side)

    def _build_open_order_payload(
        self,
        instrument_id: int,
        side: str,
        amount: float,
        stop_loss: float,
        take_profit: float,
    ) -> dict:
        return build_open_order_payload(
            instrument_id=instrument_id,
            side=side,
            amount=amount,
            stop_loss=stop_loss,
            take_profit=take_profit,
            order_currency=self.settings.base_currency,
        )

    def _open_transaction_for_side(self, side: str) -> str:
        return open_transaction_for_side(side)

    def _leverage_for_side(self, side: str) -> int:
        return leverage_for_side(side)

    # -------------------------------------------------------------------------
    # Endpoint paths
    # -------------------------------------------------------------------------

    def _open_order_path(self) -> str:
        return open_order_path(self.env)

    def _close_position_path(self, position_id: str) -> str:
        return close_position_path(self.env, position_id)

    def _demo_order_details_path(self, order_id: str) -> str:
        return demo_order_details_path(order_id)

    def _real_order_lookup_path(self) -> str:
        return real_order_lookup_path()

    def _demo_portfolio_path(self) -> str:
        return demo_portfolio_path()

    def _real_portfolio_path(self) -> str:
        return real_portfolio_path()

    # -------------------------------------------------------------------------
    # Market data
    # -------------------------------------------------------------------------

    def _find_instruments_ids(self, symbols: list[str]) -> list[int]:
        return [self._find_instrument_id(symbol) for symbol in symbols]

    def _find_instrument_id(self, symbol: str) -> int:
        instrument_id = cached_instrument_id(
            instrument_ids_by_symbol=self.instrument_ids_by_symbol,
            symbol=symbol,
        )
        if instrument_id is not None:
            return instrument_id

        payload = self._get(
            instrument_search_path(),
            params={'internalSymbolFull': symbol},
        )
        resolved_instrument_id = resolve_exact_instrument_id(symbol, payload)
        remember_instrument_id(
            instrument_ids_by_symbol=self.instrument_ids_by_symbol,
            symbol_by_instrument_id=self.symbol_by_instrument_id,
            symbol=symbol,
            instrument_id=resolved_instrument_id,
        )

        logger.info(
            'Selected eToro instrument | symbol=%s | instrument_id=%s',
            symbol,
            resolved_instrument_id,
        )

        return resolved_instrument_id

    def _get_market_rates(self, instrument_ids: list[int]) -> dict:
        return self._get(instrument_rates_path(instrument_ids))

    def _to_market_snapshot(self, symbol: str, rates_payload: dict) -> MarketSnapshot:
        return self._to_market_snapshots(rates_payload)[symbol]

    def _to_market_snapshots(self, rates_payload: dict) -> dict[str, MarketSnapshot]:
        return to_market_snapshots(
            rates_payload=rates_payload,
            symbol_by_instrument_id=self.symbol_by_instrument_id,
        )

    # -------------------------------------------------------------------------
    # Order confirmation
    # -------------------------------------------------------------------------

    def _wait_for_executed_order(
        self,
        order_id: str,
        attempts: int = 10,
        delay_seconds: float = 1.0,
    ) -> dict:
        last_lookup_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                details = self.get_order_details(order_id)
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                last_lookup_error = exc
                logger.warning(
                    'eToro order lookup failed | order_id=%s | attempt=%s/%s | error=%s',
                    order_id,
                    attempt,
                    attempts,
                    exc,
                )
                time.sleep(delay_seconds)
                continue

            executed = self._is_order_executed(details)

            logger.info(
                'eToro order lookup | order_id=%s | attempt=%s/%s | executed=%s | response=%s',
                order_id,
                attempt,
                attempts,
                executed,
                details,
            )

            if self._is_order_rejected(details):
                error_code = self._extract_order_error_code(details)
                error_message = self._extract_order_error_message(details)

                raise RuntimeError(
                    f'eToro order rejected: order_id={order_id}, '
                    f'error_code={error_code}, error_message={error_message}, '
                    f'details={details}'
                )

            if executed:
                return details

            time.sleep(delay_seconds)

        raise RuntimeError(
            f'eToro order was not executed after polling: '
            f'order_id={order_id}, last_lookup_error={last_lookup_error}'
        )

    def _wait_until_position_closed(
        self,
        position_id: str,
        attempts: int = 10,
        delay_seconds: float = 1.0,
    ) -> None:
        last_lookup_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                if not self.is_position_open(position_id):
                    logger.info(
                        'eToro position closure confirmed | position_id=%s | attempt=%s/%s',
                        position_id,
                        attempt,
                        attempts,
                    )
                    return

                logger.info(
                    'eToro position still open | position_id=%s | attempt=%s/%s',
                    position_id,
                    attempt,
                    attempts,
                )

            except (requests.RequestException, RuntimeError, ValueError) as exc:
                last_lookup_error = exc
                logger.warning(
                    'eToro position close lookup failed | position_id=%s | attempt=%s/%s | error=%s',
                    position_id,
                    attempt,
                    attempts,
                    exc,
                )

            time.sleep(delay_seconds)

        raise RuntimeError(
            f'eToro position still appears open after close confirmation: '
            f'position_id={position_id}, last_lookup_error={last_lookup_error}'
        )

    def _is_order_executed(self, payload: dict) -> bool:
        return is_order_executed(payload)

    def _is_order_rejected(self, payload: dict) -> bool:
        return is_order_rejected(payload)

    def _is_close_response_accepted(self, payload: dict, position_id: str) -> bool:
        return is_close_response_accepted(payload, position_id)

    def _contains_open_position(self, payload: dict, position_id: str) -> bool:
        return contains_open_position(payload, position_id)

    def _extract_open_positions(self, payload: dict) -> list[dict]:
        return extract_open_positions(payload)

    def _extract_order_error_code(self, payload: dict) -> int | None:
        return extract_order_error_code(payload)

    def _extract_order_error_message(self, payload: dict) -> str | None:
        return extract_order_error_message(payload)

    # -------------------------------------------------------------------------
    # Extractors
    # -------------------------------------------------------------------------

    def _extract_items(self, payload: dict | list) -> list[dict]:
        return extract_items(payload)

    def _extract_float(self, payload: dict, keys: tuple[str, ...]) -> float:
        return extract_float(payload, keys)

    def _extract_optional_float(self, payload: dict, keys: tuple[str, ...]) -> float | None:
        return extract_optional_float(payload, keys)

    def _extract_int(self, payload: dict, keys: tuple[str, ...]) -> int:
        return extract_int(payload, keys)

    def _extract_optional_int(self, payload: dict, keys: tuple[str, ...]) -> int | None:
        return extract_optional_int(payload, keys)

    def _extract_account_equity(self, payload: dict) -> float:
        return extract_account_equity(payload)

    def _extract_optional_account_equity(self, payload: dict) -> float | None:
        return extract_optional_account_equity(payload)

    def _extract_order_id(self, payload: dict) -> str:
        return extract_order_id(payload)

    def _extract_reference_id(self, payload: dict) -> str | None:
        return extract_reference_id(payload)

    def _extract_position_id_from_order_details(self, payload: dict) -> str | None:
        return extract_position_id_from_order_details(payload)
