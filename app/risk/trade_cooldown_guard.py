from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.trade_cooldown import TradeCooldownConfig, TradeCooldownEntry

if TYPE_CHECKING:
    from app.execution.trade_candidate import TradeCandidate
    from app.risk.risk_manager import RiskManager


@dataclass(frozen=True)
class TradeCooldownDecision:
    allowed: bool
    reason: str | None = None
    active_cooldown: TradeCooldownEntry | None = None
    remaining_seconds: int | None = None


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

    def check(
        self,
        *,
        symbol: str,
        side: str,
        config: TradeCooldownConfig,
        now: datetime,
    ) -> TradeCooldownDecision:
        if not config.enabled:
            return TradeCooldownDecision(allowed=True)

        normalized_side = side.strip().upper()
        if normalized_side not in ('BUY', 'SELL'):
            return TradeCooldownDecision(allowed=True)

        active_cooldown = self.store.find_active(
            symbol=symbol,
            side=normalized_side,
            now=now,
        )

        if active_cooldown is None:
            return TradeCooldownDecision(allowed=True)

        return TradeCooldownDecision(
            allowed=False,
            reason=f'cooldown_after_{active_cooldown.close_reason.value}',
            active_cooldown=active_cooldown,
            remaining_seconds=active_cooldown.remaining_seconds(now),
        )

    def filter_candidates(
        self,
        *,
        candidates: list['TradeCandidate'],
        risk_manager: 'RiskManager',
        now: datetime,
    ) -> TradeCooldownFilterResult:
        selected_candidates: list['TradeCandidate'] = []
        rejected_candidates: list[RejectedCooldownCandidate] = []

        for candidate in candidates:
            risk_profile = risk_manager.risk_profile_for(candidate.symbol)
            decision = self.check(
                symbol=candidate.symbol,
                side=candidate.signal.action,
                config=risk_profile.trade_cooldown,
                now=now,
            )

            if decision.allowed:
                selected_candidates.append(candidate)
                continue

            rejected_candidates.append(
                RejectedCooldownCandidate(
                    candidate=candidate,
                    decision=decision,
                )
            )

        return TradeCooldownFilterResult(
            selected_candidates=selected_candidates,
            rejected_candidates=rejected_candidates,
        )
