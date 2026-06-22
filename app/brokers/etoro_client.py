import logging
from dataclasses import dataclass

import requests

from app.brokers.base import BrokerClient
from app.config.settings import Settings
from app.market.models import MarketSnapshot

logger = logging.getLogger(__name__)


@dataclass
class EtoroClient(BrokerClient):
    settings: Settings

    @property
    def headers(self) -> dict[str, str]:
        return {
            'x-api-key': self.settings.etoro_api_key,
            'x-user-key': self.settings.etoro_user_key,
            'Content-Type': 'application/json',
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f'{self.settings.etoro_api_base_url.rstrip("/")}/{path.lstrip("/")}'
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        # TODO: replace path/field mapping with the exact eToro market-data endpoint.
        # This placeholder intentionally fails loudly instead of trading on fake data.
        raise NotImplementedError('Map eToro market-data endpoint before using real broker data.')

    def get_account_equity(self) -> float:
        # TODO: map eToro portfolio/account endpoint.
        raise NotImplementedError('Map eToro account endpoint before using real broker data.')

    def open_position(self, symbol: str, side: str, amount: float, stop_loss: float, take_profit: float) -> str:
        if self.settings.ear_mode != 'real':
            raise RuntimeError('Real broker execution is disabled unless EAR_MODE=real.')
        # TODO: map eToro order endpoint.
        raise NotImplementedError('Map eToro order endpoint before placing real orders.')

    def close_position(self, position_id: str) -> None:
        if self.settings.ear_mode != 'real':
            raise RuntimeError('Real broker execution is disabled unless EAR_MODE=real.')
        # TODO: map eToro close-position endpoint.
        raise NotImplementedError('Map eToro close endpoint before closing real orders.')
