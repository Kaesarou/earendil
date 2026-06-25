from typing import Protocol

from app.market.models import Candle
from app.strategies.signals import Signal


class InvestmentStrategy(Protocol):
    def on_candle(self, candle: Candle) -> Signal:
        raise NotImplementedError