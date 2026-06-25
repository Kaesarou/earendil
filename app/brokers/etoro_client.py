import logging
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
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    
    def _post(self, path: str, payload: dict) -> dict:
        url = f'{self.settings.etoro_api_base_url.rstrip("/")}/{path.lstrip("/")}'
        response = requests.post(url, headers=self.headers, json=payload, timeout=10)
        response.raise_for_status()

        if not response.content:
            return {}

        return response.json()

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        instrument_id = self._find_instrument_id(symbol)
        rates_payload = self._get_market_rates(instrument_id)

        return self._to_market_snapshot(
            symbol=symbol,
            rates_payload=rates_payload,
        )
    
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

        logger.info(
            "Selected eToro instrument | symbol=%s | display_name=%s | instrument_id=%s | current_rate=%s",
            instrument.get("internalSymbolFull"),
            instrument.get("internalInstrumentDisplayName"),
            instrument.get("internalInstrumentId") or instrument.get("instrumentId"),
            instrument.get("currentRate"),
        )

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
        
        return int(instrument_id)

    def _get_market_rates(self, instrument_id: int) -> dict:
        rates_payload = self._get(
            '/api/v1/market-data/instruments/rates',
            params={'instrumentIds': instrument_id},
        )
        return rates_payload

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

    def get_account_equity(self) -> float:
        # US-1: no real account mapping yet.
        # In paper mode, main.py currently uses FakeBrokerClient.
        # This method will be mapped in a later US when we work on portfolio/account data.
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
            'symbol': symbol,
            'instrumentId': instrument_id,
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

        response = self._post(self._open_order_path(), payload)

        logger.info('eToro order response: %s', response)

        position_id = self._extract_position_id(response)
        self.position_instruments[position_id] = instrument_id

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

        response = self._post(
            f'/api/v1/trading/execution/market-close-orders/positions/{position_id}',
            payload,
        )

        logger.info('eToro close position response: %s', response)
        self.position_instruments.pop(position_id, None)

    def _ensure_real_trading_enabled(self) -> None:
        if self.settings.ear_mode != 'real':
            raise RuntimeError('Real broker execution is disabled unless EAR_MODE=real.')

        if not self.settings.real_trading_enabled:
            raise RuntimeError(
                'Real broker execution is disabled unless REAL_TRADING_ENABLED=true.'
            )
        
    def _open_order_path(self) -> str:
        if self.settings.etoro_env == 'demo':
            return '/api/v2/trading/execution/demo/orders'

        return '/api/v2/trading/execution/orders'

    def _extract_position_id(self, payload: dict) -> str:
        for key in (
            'positionId',
            'PositionId',
            'positionID',
            'PositionID',
            'id',
            'orderId',
            'OrderId',
            'orderID',
            'OrderID',
        ):
            value = payload.get(key)
            if value is not None:
                return str(value)

        for key in ('data', 'Data', 'item', 'Item', 'order', 'Order', 'position', 'Position'):
            value = payload.get(key)
            if isinstance(value, dict):
                try:
                    return self._extract_position_id(value)
                except ValueError:
                    pass

        raise ValueError(f'Unable to extract position id from eToro response: {payload}')