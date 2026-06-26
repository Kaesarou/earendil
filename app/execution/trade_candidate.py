from dataclasses import dataclass

from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal


@dataclass(frozen=True)
class TradeCandidate:
    symbol: str
    snapshot: MarketSnapshot
    candle: Candle
    signal: Signal
    score: float
    rank_reason: str