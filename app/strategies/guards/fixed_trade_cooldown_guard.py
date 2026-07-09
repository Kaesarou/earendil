from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.persistence.closed_trade_memory_store import ClosedTradeMemoryStore
from app.risk.trade_cooldown import ClosedTradeMemoryEntry, TradeCooldownConfig

if TYPE_CHECKING:
    from app.execution.trade_candidate import TradeCandidate


@dataclass(frozen=True)
class FixedTradeCooldownDecision:
    allowed: bool
    reason: str | None = None
    active_cooldown: ClosedTradeMemoryEntry | None = None
    remaining_seconds: int | None = None


@dataclass(frozen=True)
class RejectedFixedCooldownCandidate:
    candidate: 'TradeCandidate'
    decision: FixedTradeCooldownDecision


@dataclass(frozen=True)
class FixedTradeCooldownFilterResult:
    selected_candidates: list['TradeCandidate']
    rejected_candidates: list[RejectedFixedCooldownCandidate]


class FixedTradeCooldownGuard:
    def __init__(self, store: ClosedTradeMemoryStore):
        self.store = store

    def check(
        self,
        *,
        symbol: str,
        side: str,
        config: TradeCooldownConfig,
        now: datetime,
    ) -> FixedTradeCooldownDecision:
        if not config.enabled:
            return FixedTradeCooldownDecision(allowed=True)

        normalized_side = side.strip().upper()
        if normalized_side not in ('BUY', 'SELL'):
            return FixedTradeCooldownDecision(allowed=True)

        active_cooldown = self.store.find_active_cooldown(
            symbol=symbol,
            side=normalized_side,
            now=now,
        )

        if active_cooldown is None:
            return FixedTradeCooldownDecision(allowed=True)

        return FixedTradeCooldownDecision(
            allowed=False,
            reason=f'cooldown_after_{active_cooldown.close_reason.value}',
            active_cooldown=active_cooldown,
            remaining_seconds=active_cooldown.remaining_seconds(now),
        )

    def filter_candidates(
        self,
        *,
        candidates: list['TradeCandidate'],
        config_for_candidate: Callable[['TradeCandidate'], TradeCooldownConfig],
        now: datetime,
    ) -> FixedTradeCooldownFilterResult:
        selected_candidates: list['TradeCandidate'] = []
        rejected_candidates: list[RejectedFixedCooldownCandidate] = []

        for candidate in candidates:
            decision = self.check(
                symbol=candidate.symbol,
                side=candidate.signal.action,
                config=config_for_candidate(candidate),
                now=now,
            )

            if decision.allowed:
                selected_candidates.append(candidate)
                continue

            rejected_candidates.append(
                RejectedFixedCooldownCandidate(
                    candidate=candidate,
                    decision=decision,
                )
            )

        return FixedTradeCooldownFilterResult(
            selected_candidates=selected_candidates,
            rejected_candidates=rejected_candidates,
        )
