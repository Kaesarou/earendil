import logging
import time
from dataclasses import dataclass, field
from uuid import uuid4

import requests

from app.brokers.base import BrokerClient
from app.config.settings import Settings
from app.market.models import MarketSnapshot

logger = logging.getLogger(__name__)


@dataclass
class EtoroClient(BrokerClient):
    settings: Settings
    position_instruments: dict[str, int] = field(default_factory=dict)

    # -------------------------------------------------------------------------
    # Public broker API
    # -------------------------------------------------------------------------

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        instrument_id = self._find_instrument_id(symbol)
        rates_payload = self._get_market_rates(instrument_id)

        return self._to_market_snapshot(
            symbol=symbol,
            rates_payload=rates_payload,
        )

    def get_account_equity(self) -> float:
        # Temporary MVP fallback.
        # TODO: map real eToro portfolio/equity endpoint before real production usage.
        return 50.0

    def open_position(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_loss: float,
        take_profit: float,
    ) -> str:
        self._ensure_real_trading_enabled()

        if side != 'BUY':
            raise ValueError(f'Unsupported side for eToro MVP: {side}')

        instrument_id = self._find_instrument_id(symbol)

        payload = {
            'action': 'open',
            'transaction': 'buy',
            'InstrumentID': instrument_id,
            'orderType': 'mkt',
            'leverage': 1,
            'amount': amount,
            'orderCurrency': self.settings.base_currency.lower(),
        }

        logger.warning(
            'Sending eToro order | env=%s | symbol=%s | instrument_id=%s | amount=%s | stop_loss=%s | take_profit=%s',
            self.settings.etoro_env,
            symbol,
            instrument_id,
            amount,
            stop_loss,
            take_profit,
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
            'eToro position confirmed | order_id=%s | position_id=%s | instrument_id=%s',
            order_id,
            position_id,
            instrument_id,
        )

        return position_id

    def close_position(self, position_id: str) -> None:
        self._ensure_real_trading_enabled()

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
        if self.settings.etoro_env == 'demo':
            return self._get(self._demo_order_details_path(order_id))

        return self._get(
            self._real_order_lookup_path(),
            params={'orderId': order_id},
        )

    def get_portfolio(self) -> dict:
        if self.settings.etoro_env == 'demo':
            return self._get(self._demo_portfolio_path())

        return self._get(self._real_portfolio_path())

    def is_position_open(self, position_id: str) -> bool:
        portfolio = self.get_portfolio()
        return self._contains_open_position(portfolio, position_id)

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
        url = f'{self.settings.etoro_api_base_url.rstrip("/")}/{path.lstrip("/")}'

        response = requests.get(
            url,
            headers=self.headers,
            params=params,
            timeout=10,
        )

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

    def _post(self, path: str, payload: dict) -> dict:
        url = f'{self.settings.etoro_api_base_url.rstrip("/")}/{path.lstrip("/")}'

        response = requests.post(
            url,
            headers=self.headers,
            json=payload,
            timeout=10,
        )

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

    def _ensure_real_trading_enabled(self) -> None:
        if self.settings.ear_mode != 'real':
            raise RuntimeError('Real broker execution is disabled unless EAR_MODE=real.')

        if not self.settings.real_trading_enabled:
            raise RuntimeError(
                'Real broker execution is disabled unless REAL_TRADING_ENABLED=true.'
            )

    # -------------------------------------------------------------------------
    # Endpoint paths
    # -------------------------------------------------------------------------

    def _open_order_path(self) -> str:
        if self.settings.etoro_env == 'demo':
            return '/api/v2/trading/execution/demo/orders'

        return '/api/v2/trading/execution/orders'

    def _close_position_path(self, position_id: str) -> str:
        if self.settings.etoro_env == 'demo':
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

    def _find_instrument_id(self, symbol: str) -> int:
        payload = self._get(
            '/api/v1/market-data/search',
            params={'internalSymbolFull': symbol},
        )

        items = self._extract_items(payload)
        normalized_symbol = symbol.upper()

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

        logger.info(
            'Selected eToro instrument | symbol=%s | display_name=%s | instrument_id=%s | current_rate=%s',
            instrument.get('internalSymbolFull'),
            instrument.get('internalInstrumentDisplayName'),
            instrument_id,
            instrument.get('currentRate'),
        )

        return int(instrument_id)

    def _get_market_rates(self, instrument_id: int) -> dict:
        return self._get(
            '/api/v1/market-data/instruments/rates',
            params={'instrumentIds': instrument_id},
        )

    def _to_market_snapshot(self, symbol: str, rates_payload: dict) -> MarketSnapshot:
        rate = self._first_item(rates_payload)

        bid = self._extract_float(rate, ('Bid', 'bid', 'bidPrice'))
        ask = self._extract_float(rate, ('Ask', 'ask', 'askPrice'))

        last = self._extract_optional_float(
            rate,
            ('Last', 'last', 'lastPrice', 'Price', 'price'),
        )

        if last is None:
            last = (bid + ask) / 2

        return MarketSnapshot.now(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
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
        for attempt in range(1, attempts + 1):
            try:
                details = self.get_order_details(order_id)
            except requests.HTTPError as exc:
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

        raise RuntimeError(f'eToro order was not executed after polling: order_id={order_id}')

    def _wait_until_position_closed(
        self,
        position_id: str,
        attempts: int = 10,
        delay_seconds: float = 1.0,
    ) -> None:
        for attempt in range(1, attempts + 1):
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

            time.sleep(delay_seconds)

        raise RuntimeError(
            f'eToro position still appears open after close confirmation: position_id={position_id}'
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

    def _first_item(self, payload: dict) -> dict:
        for key in ('data', 'items', 'Data', 'Items', 'instruments', 'rates'):
            value = payload.get(key)

            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, dict):
                    return first

            if isinstance(value, dict):
                return value

        if isinstance(payload, list) and payload:
            first = payload[0]
            if isinstance(first, dict):
                return first

        if isinstance(payload, dict):
            return payload

        raise ValueError(f'Unable to extract item from payload={payload}')

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