import logging
import time
from uuid import uuid4

import requests

from app.brokers.base import BrokerClient
from app.brokers.etoro.order_payload_builder import (
    build_open_order_payload,
    leverage_for_side,
    open_transaction_for_side,
)
from app.config.settings import Settings
from app.market.models import MarketSnapshot

logger = logging.getLogger(__name__)


class EtoroClient(BrokerClient):
    settings: Settings
    env:str 
    position_instruments: dict[str, int]
    instrument_ids_by_symbol: dict[str, int]
    symbol_by_instrument_id: dict[int, str]
    etoro_api_base_url = 'https://public-api.etoro.com'

    def __init__(self, settings: Settings):
        self.settings = settings
        self.env = settings.broker.split('_')[-1]
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
     
    #Pour l'instant on est limité à 100 symbols
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

        self.position_instruments[position_id] = instrument_id

        logger.info(
            'eToro position confirmed | order_id=%s | position_id=%s | instrument_id=%s | side=%s',
            order_id,
            position_id,
            instrument_id,
            normalized_side,
        )

        return position_id

    def close_position(self, position_id: str) -> None:

        instrument_id = self.position_instruments.get(position_id)
        if instrument_id is None:
            raise ValueError(
                f'Cannot close eToro position without known instrument id: {position_id}'
            )

        payload = {
            'InstrumentId': instrument_id,
            'UnitsToDeduct': None,
        }

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

            self.position_instruments.pop(position_id, None)
            return

        close_details = self._wait_for_executed_order(close_order_id)
        self._wait_until_position_closed(position_id)

        logger.info(
            'eToro close confirmed | position_id=%s | close_order_id=%s | details=%s',
            position_id,
            close_order_id,
            close_details,
        )

        self.position_instruments.pop(position_id, None)

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
        self.position_instruments[position_id] = instrument_id

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
        return {
            'x-request-id': str(uuid4()),
            'x-api-key': self.settings.etoro_api_key,
            'x-user-key': self.settings.etoro_user_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f'{self.etoro_api_base_url.rstrip("/")}/{path.lstrip("/")}'
        max_attempts = 3
        retry_status_codes = {429, 500, 502, 503, 504}

        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=10,
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

                time.sleep(attempt)
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

                time.sleep(attempt)
                continue

            if response.status_code in retry_status_codes and attempt < max_attempts:
                logger.warning(
                    'eToro GET retryable error | attempt=%s/%s | status=%s | url=%s | params=%s | response=%s',
                    attempt,
                    max_attempts,
                    response.status_code,
                    url,
                    params,
                    response.text,
                )

                time.sleep(attempt)
                continue

            if not response.ok:
                logger.error(
                    'eToro GET failed | status=%s | url=%s | params=%s | response=%s',
                    response.status_code,
                    url,
                    params,
                    response.text,
                )
                response.raise_for_status()

            if not response.content:
                return {}

            return response.json()

        raise RuntimeError(f'eToro GET failed after retries | url={url} | params={params}')

    def _post(self, path: str, payload: dict) -> dict:
        url = f'{self.etoro_api_base_url.rstrip("/")}/{path.lstrip("/")}'

        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=10,
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
            response.raise_for_status()

        if not response.content:
            return {}

        return response.json()

    # -------------------------------------------------------------------------
    # Safety guards
    # -------------------------------------------------------------------------

    def _normalize_side(self, side: str) -> str:
        return side.strip().upper()

    def _ensure_side_is_allowed(self, side: str) -> None:
        if side == 'BUY':
            return

        if side == 'SELL':
            return

        raise ValueError(f'Unsupported side for eToro order: {side}')

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
        if self.env == 'demo':
            return '/api/v2/trading/execution/demo/orders'

        return '/api/v2/trading/execution/orders'

    def _close_position_path(self, position_id: str) -> str:
        if self.env == 'demo':
            return f'/api/v1/trading/execution/demo/market-close-orders/positions/{position_id}'

        return f'/api/v1/trading/execution/market-close-orders/positions/{position_id}'

    def _demo_order_details_path(self, order_id: str) -> str:
        return f'/api/v1/trading/info/demo/orders/{order_id}'

    def _real_order_lookup_path(self) -> str:
        return '/api/v2/trading/info/orders:lookup'

    def _demo_portfolio_path(self) -> str:
        return '/api/v1/trading/info/demo/portfolio'

    def _real_portfolio_path(self) -> str:
        return '/api/v1/trading/info/portfolio'

    # -------------------------------------------------------------------------
    # Market data
    # -------------------------------------------------------------------------
    def _find_instruments_ids(self, symbols: list[str]) -> list[int]:
        ids = []
        for symbol in symbols:
            ids.append(self._find_instrument_id(symbol))
        return ids


    def _find_instrument_id(self, symbol: str) -> int:
        normalized_symbol = symbol.upper()

        cached_instrument_id = self.instrument_ids_by_symbol.get(normalized_symbol)
        if cached_instrument_id is not None:
            return cached_instrument_id

        payload = self._get(
            '/api/v1/market-data/search',
            params={'internalSymbolFull': symbol},
        )

        items = self._extract_items(payload)

        exact_matches = [
            item for item in items
            if str(item.get('internalSymbolFull', '')).upper() == normalized_symbol
        ]

        if not exact_matches:
            candidates = [
                {
                    'internalSymbolFull': item.get('internalSymbolFull'),
                    'displayName': item.get('internalInstrumentDisplayName'),
                    'instrumentId': item.get('internalInstrumentId') or item.get('instrumentId'),
                    'currentRate': item.get('currentRate'),
                }
                for item in items[:10]
            ]

            raise ValueError(
                f'No exact eToro instrument match found for symbol={symbol}. '
                f'Candidates={candidates}'
            )

        instrument = exact_matches[0]
        instrument_id = (
            instrument.get('internalInstrumentId')
            or instrument.get('instrumentId')
            or instrument.get('InstrumentID')
            or instrument.get('instrumentID')
            or instrument.get('id')
        )

        if instrument_id is None:
            raise ValueError(
                f'Unable to find instrument id for symbol={symbol}. Instrument={instrument}'
            )

        resolved_instrument_id = int(instrument_id)
        self.instrument_ids_by_symbol[normalized_symbol] = resolved_instrument_id
        self.symbol_by_instrument_id[resolved_instrument_id] = normalized_symbol

        logger.info(
            'Selected eToro instrument | symbol=%s | display_name=%s | instrument_id=%s | current_rate=%s',
            instrument.get('internalSymbolFull'),
            instrument.get('internalInstrumentDisplayName'),
            resolved_instrument_id,
            instrument.get('currentRate'),
        )

        return resolved_instrument_id

    def _get_market_rates(self, instrument_ids: list[int]) -> dict:
        joined_instrument_ids = ','.join(
            str(instrument_id)
            for instrument_id in instrument_ids
        )

        return self._get(
            f'/api/v1/market-data/instruments/rates?instrumentIds={joined_instrument_ids}',
        )
     
    def _to_market_snapshot(self, symbol: str, rates_payload: dict) -> MarketSnapshot:
        return self._to_market_snapshots(rates_payload)[symbol]

    def _to_market_snapshots(self, rates_payload: dict) -> dict[str, MarketSnapshot]:
        
        result: dict[str, MarketSnapshot] = {}
        rates = rates_payload['rates']

        for rate in rates:
            instrument_id = self._extract_int(rate, ('instrumentID', 'instrumentId'))

            symbol = self.symbol_by_instrument_id.get(instrument_id)
            if symbol is None:
                raise ValueError(f'Unable to find cached symbol by instrument_id={instrument_id}.')

            bid = self._extract_float(rate, ('Bid', 'bid', 'bidPrice'))
            ask = self._extract_float(rate, ('Ask', 'ask', 'askPrice'))

            last = self._extract_optional_float(
                rate,
                ('Last', 'last', 'lastPrice', 'Price', 'price', 'lastExecution'),
            )

            if last is None:
                last = (bid + ask) / 2

            result[symbol] = MarketSnapshot.now(
                symbol=symbol,
                bid=bid,
                ask=ask,
                last=last,
            )
        return result

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
        status = payload.get('status')

        if isinstance(status, dict):
            status_name = str(status.get('name', '')).lower()
            status_id = status.get('id')
            status_error_code = status.get('errorCode')

            if status_error_code not in (None, 0):
                return False

            if status_name == 'executed' or status_id == 1:
                return True

        error_code = payload.get('errorCode')
        if error_code not in (None, 0):
            return False

        status_id = payload.get('statusID')
        if status_id in (1, 3):
            return True

        return self._extract_position_id_from_order_details(payload) is not None

    def _is_order_rejected(self, payload: dict) -> bool:
        error_code = self._extract_order_error_code(payload)
        if error_code not in (None, 0):
            return True

        status = payload.get('status')
        if isinstance(status, dict):
            status_error_code = status.get('errorCode')
            if status_error_code not in (None, 0):
                return True

            status_name = str(status.get('name', '')).lower()
            if status_name in ('rejected', 'failed', 'cancelled', 'canceled', 'error'):
                return True

        return False

    def _is_close_response_accepted(self, payload: dict, position_id: str) -> bool:
        order_for_close = payload.get('orderForClose')

        if not isinstance(order_for_close, dict):
            return False

        response_position_id = (
            order_for_close.get('positionID')
            or order_for_close.get('positionId')
            or order_for_close.get('PositionID')
            or order_for_close.get('PositionId')
        )

        if str(response_position_id) != str(position_id):
            return False

        status_id = order_for_close.get('statusID') or order_for_close.get('statusId')

        return status_id == 1

    def _contains_open_position(self, payload: dict, position_id: str) -> bool:
        open_positions = self._extract_open_positions(payload)

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

    def _extract_open_positions(self, payload: dict) -> list[dict]:
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
            return self._extract_open_positions(data)

        return []

    def _extract_order_error_code(self, payload: dict) -> int | None:
        error_code = payload.get('errorCode')

        if error_code is not None:
            return int(error_code)

        status = payload.get('status')
        if isinstance(status, dict):
            status_error_code = status.get('errorCode')
            if status_error_code is not None:
                return int(status_error_code)

        return None

    def _extract_order_error_message(self, payload: dict) -> str | None:
        error_message = payload.get('errorMessage')

        if error_message:
            return str(error_message)

        status = payload.get('status')
        if isinstance(status, dict):
            status_error_message = status.get('errorMessage')
            if status_error_message:
                return str(status_error_message)

        return None

    # -------------------------------------------------------------------------
    # Extractors
    # -------------------------------------------------------------------------

    def _extract_items(self, payload: dict) -> list[dict]:
        for key in ('items', 'data', 'Data', 'Items', 'instruments', 'rates'):
            value = payload.get(key)

            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

            if isinstance(value, dict):
                return [value]

        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        return []


    def _extract_float(self, payload: dict, keys: tuple[str, ...]) -> float:
        value = self._extract_optional_float(payload, keys)

        if value is None:
            raise ValueError(f'Unable to extract required float keys={keys}. Payload={payload}')

        return value

    def _extract_optional_float(self, payload: dict, keys: tuple[str, ...]) -> float | None:
        for key in keys:
            value = payload.get(key)
            if value is not None:
                return float(value)

        return None
     
    def _extract_int(self, payload: dict, keys: tuple[str, ...]) -> int:
        value = self._extract_optional_int(payload, keys)

        if value is None:
            raise ValueError(f'Unable to extract required int keys={keys}. Payload={payload}')

        return value
     
    def _extract_optional_int(self, payload: dict, keys: tuple[str, ...]) -> int | None:
        for key in keys:
            value = payload.get(key)
            if value is not None:
                return int(value)

        return None
     
    def _extract_account_equity(self, payload: dict) -> float:
        equity = self._extract_optional_account_equity(payload)

        if equity is None:
            raise ValueError(f'Unable to extract account equity from eToro portfolio: {payload}')

        if equity <= 0:
            raise ValueError(f'Invalid eToro account equity={equity}. Portfolio={payload}')

        return equity


    def _extract_optional_account_equity(self, payload: dict) -> float | None:
        for key in (
            'equity',
            'Equity',
            'accountEquity',
            'AccountEquity',
            'netLiquidationValue',
            'NetLiquidationValue',
            'netLiq',
            'NetLiq',
            'balance',
            'Balance',
            'cash',
            'Cash',
            'credit',
            'Credit',
            'availableBalance',
            'AvailableBalance',
            'availableCash',
            'AvailableCash',
        ):
            value = payload.get(key)
            if value is not None:
                return float(value)
     
        for key in (
            'clientPortfolio',
            'ClientPortfolio',
            'portfolio',
            'Portfolio',
            'account',
            'Account',
            'cashAvailable',
            'CashAvailable',
            'data',
            'Data',
        ):
            value = payload.get(key)
     
            if isinstance(value, dict):
                nested_equity = self._extract_optional_account_equity(value)
                if nested_equity is not None:
                    return nested_equity
     
        return None

    def _extract_order_id(self, payload: dict) -> str:
        for key in ('orderId', 'OrderId', 'orderID', 'OrderID'):
            value = payload.get(key)
            if value is not None:
                return str(value)

        for key in (
            'orderForClose',
            'OrderForClose',
            'data',
            'Data',
            'order',
            'Order',
        ):
            value = payload.get(key)
            if isinstance(value, dict):
                try:
                    return self._extract_order_id(value)
                except ValueError:
                    pass

        raise ValueError(f'Unable to extract order id from eToro response: {payload}')

    def _extract_reference_id(self, payload: dict) -> str | None:
        for key in ('referenceId', 'ReferenceId', 'referenceID', 'ReferenceID'):
            value = payload.get(key)
            if value is not None:
                return str(value)

        return None

    def _extract_position_id_from_order_details(self, payload: dict) -> str | None:
        direct_position_id = (
            payload.get('positionId')
            or payload.get('PositionId')
            or payload.get('positionID')
            or payload.get('PositionID')
        )

        if direct_position_id is not None:
            return str(direct_position_id)

        position_executions = payload.get('positionExecutions')
        if isinstance(position_executions, list):
            for execution in position_executions:
                if not isinstance(execution, dict):
                    continue

                position_id = (
                    execution.get('positionId')
                    or execution.get('PositionId')
                    or execution.get('positionID')
                    or execution.get('PositionID')
                )

                if position_id is not None:
                    return str(position_id)

        positions = payload.get('positions')
        if isinstance(positions, list):
            for position in positions:
                if not isinstance(position, dict):
                    continue

                position_id = (
                    position.get('positionId')
                    or position.get('PositionId')
                    or position.get('positionID')
                    or position.get('PositionID')
                )

                if position_id is not None:
                    return str(position_id)

        for key in ('position', 'Position', 'data', 'Data', 'order', 'Order'):
            value = payload.get(key)
            if isinstance(value, dict):
                position_id = self._extract_position_id_from_order_details(value)
                if position_id is not None:
                    return position_id

        return None
