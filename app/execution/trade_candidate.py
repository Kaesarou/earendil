from dataclasses import dataclass, field
from typing import Any

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
    session_key: str
    base_score: float = 0.0
    exhaustion_penalty: float = 0.0
    late_entry_risk: float = 0.0
    entry_quality_metadata: dict[str, Any] = field(default_factory=dict)
