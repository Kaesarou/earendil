from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.market.models import Candle, MarketSnapshot
from app.strategies.signals import Signal


if TYPE_CHECKING:
    from app.instruments.models import EntryDecisionConfig
    from app.market.market_context import CandidateMarketContext
    from app.market.multi_timeframe import MultiTimeframeContext


@dataclass(frozen=True)
class TradeCandidate:
    symbol: str
    snapshot: MarketSnapshot
    candle: Candle
    signal: Signal
    score: float
    rank_reason: str
    session_key: str = ''
    base_score: float = 0.0
    exhaustion_penalty: float = 0.0
    late_entry_risk: float = 0.0
    late_entry_severity: str = 'LOW'
    entry_quality_metadata: dict[str, Any] = field(default_factory=dict)
    sell_score_metadata: dict[str, Any] = field(default_factory=dict)
    sell_specific_penalty: float = 0.0
    tp_feasibility_metadata: dict[str, Any] = field(default_factory=dict)
    tp_feasibility_penalty: float = 0.0
    tp_feasibility_hard_rejection_reason: str | None = None
    tp_before_sl_probability: float | None = None
    tp_before_sl_probability_band: str | None = None
    tp_probability_model_version: str | None = None
    break_even_probability: float | None = None
    net_expected_value_percent: float | None = None
    probability_edge: float | None = None
    tp_probability_metadata: dict[str, Any] = field(default_factory=dict)
    candidate_id: str = ''
    origin_candidate_id: str = ''
    pending_entry_id: str | None = None
    market_context: CandidateMarketContext | None = None
    multi_timeframe_context: MultiTimeframeContext | None = None
    entry_decision_config: EntryDecisionConfig | None = None
