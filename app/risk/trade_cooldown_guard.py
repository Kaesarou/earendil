from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.trade_cooldown import ClosedTradeMemoryEntry, TradeCooldownConfig
from app.strategies.guards.fixed_trade_cooldown_guard import FixedTradeCooldownGuard
from app.strategies.guards.post_tp_reentry_guard import PostTpReentryConfig, PostTpReentryGuard

if TYPE_CHECKING:
    from app.execution.trade_candidate import TradeCandidate
    from app.risk.risk_manager import RiskManager


@dataclass(frozen=True)
class TradeCooldownDecision:
    allowed: bool
    reason: str | None = None
    active_cooldown: ClosedTradeMemoryEntry | None = None
    remaining_seconds: int | None = None
    details: dict | None = None


@dataclass(frozen=True)
class RejectedCooldownCandidate:
    candidate: 'TradeCandidate'
    decision: TradeCooldownDecision


@dataclass(frozen=True)
class TradeCooldownFilterResult:
    selected_candidates: list['TradeCandidate']
    rejected_candidates: list[RejectedCooldownCandidate]


class TradeCooldownGuard:
    def __init__(self, store: TradeCooldownStore):
        self.store = store
        self.fixed_guard = FixedTradeCooldownGuard(store)
        self.post_tp_reentry_guard = PostTpReentryGuard(store)

    def check(
        self,
        *,
        symbol: str,
        side: str,
        config: TradeCooldownConfig,
        now: datetime,
    ) -> TradeCooldownDecision:
        decision = self.fixed_guard.check(symbol=symbol, side=side, config=config, now=now)
        return TradeCooldownDecision(
            allowed=decision.allowed,
            reason=decision.reason,
            active_cooldown=decision.active_cooldown,
            remaining_seconds=decision.remaining_seconds,
        )

    def filter_candidates(
        self,
        *,
        candidates: list['TradeCandidate'],
        risk_manager: 'RiskManager',
        now: datetime,
    ) -> TradeCooldownFilterResult:
        fixed_result = self.fixed_guard.filter_candidates(
            candidates=candidates,
            config_for_candidate=lambda candidate: risk_manager.risk_profile_for(
                candidate.symbol
            ).trade_cooldown,
            now=now,
        )
        rejected_candidates = [
            RejectedCooldownCandidate(
                candidate=rejected.candidate,
                decision=TradeCooldownDecision(
                    allowed=False,
                    reason=rejected.decision.reason,
                    active_cooldown=rejected.decision.active_cooldown,
                    remaining_seconds=rejected.decision.remaining_seconds,
                ),
            )
            for rejected in fixed_result.rejected_candidates
        ]

        post_tp_result = self.post_tp_reentry_guard.filter_candidates(
            candidates=fixed_result.selected_candidates,
            config_for_candidate=lambda candidate: self._post_tp_config_for(candidate, risk_manager),
            now=now,
        )
        rejected_candidates.extend(
            RejectedCooldownCandidate(
                candidate=rejected.candidate,
                decision=TradeCooldownDecision(
                    allowed=False,
                    reason=rejected.decision.reason,
                    active_cooldown=rejected.decision.previous_trade,
                    details=rejected.decision.details,
                ),
            )
            for rejected in post_tp_result.rejected_candidates
        )

        return TradeCooldownFilterResult(
            selected_candidates=post_tp_result.selected_candidates,
            rejected_candidates=rejected_candidates,
        )

    def _post_tp_config_for(
        self,
        candidate: 'TradeCandidate',
        risk_manager: 'RiskManager',
    ) -> PostTpReentryConfig:
        asset_class = risk_manager.instrument_profile_for(candidate.symbol).asset_class
        asset_class_value = getattr(asset_class, 'value', str(asset_class))
        smart_watch_minutes = 120 if asset_class_value == 'CRYPTO' else 60
        return PostTpReentryConfig(smart_watch_minutes=smart_watch_minutes)
