from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.execution.trade_candidate import TradeCandidate


@dataclass
class _DecisionWindow:
    closed_at: datetime
    expected_symbols: set[str]
    completed_symbols: set[str] = field(default_factory=set)
    candidates: list[TradeCandidate] = field(default_factory=list)


@dataclass(frozen=True)
class DecisionWindowBatch:
    closed_at: datetime
    candidates: tuple[TradeCandidate, ...]
    expected_symbols: tuple[str, ...]
    completed_symbols: tuple[str, ...]
    missing_symbols: tuple[str, ...]
    finalization_reason: str


class DecisionWindowCoordinator:
    def __init__(self, *, grace_seconds: float, finalized_capacity: int = 512) -> None:
        self.grace_seconds = grace_seconds
        self._windows: dict[datetime, _DecisionWindow] = {}
        self._finalized: set[datetime] = set()
        self._finalized_order: deque[datetime] = deque()
        self._finalized_capacity = finalized_capacity

    def reset_symbol(self, symbol: str) -> None:
        normalized = symbol.strip().upper()
        for window in self._windows.values():
            window.expected_symbols.discard(normalized)
            window.completed_symbols.discard(normalized)
            window.candidates = [
                candidate
                for candidate in window.candidates
                if candidate.symbol != normalized
            ]

    def record(
        self,
        *,
        closed_at: datetime,
        symbol: str,
        expected_symbols: list[str],
        candidate: TradeCandidate | None,
    ) -> bool:
        key = _as_utc(closed_at)
        if key in self._finalized:
            return False
        window = self._windows.setdefault(
            key,
            _DecisionWindow(
                closed_at=key,
                expected_symbols={
                    item.strip().upper() for item in expected_symbols
                },
            ),
        )
        window.expected_symbols.update(
            item.strip().upper() for item in expected_symbols
        )
        window.completed_symbols.add(symbol.strip().upper())
        if candidate is not None:
            window.candidates.append(candidate)
        return True

    def pop_ready(self, *, now: datetime) -> list[list[TradeCandidate]]:
        return [
            list(batch.candidates)
            for batch in self.pop_ready_batches(now=now)
        ]

    def pop_ready_batches(self, *, now: datetime) -> list[DecisionWindowBatch]:
        actual_now = _as_utc(now)
        ready: list[tuple[datetime, str]] = []
        for key, window in self._windows.items():
            complete = window.expected_symbols.issubset(
                window.completed_symbols
            )
            expired = actual_now >= window.closed_at + timedelta(
                seconds=self.grace_seconds
            )
            if complete:
                ready.append((key, 'all_symbols_completed'))
            elif expired:
                ready.append((key, 'grace_expired'))

        result: list[DecisionWindowBatch] = []
        for key, reason in sorted(ready, key=lambda item: item[0]):
            window = self._windows.pop(key)
            self._remember_finalized(key)
            expected = set(window.expected_symbols)
            completed = set(window.completed_symbols)
            result.append(
                DecisionWindowBatch(
                    closed_at=window.closed_at,
                    candidates=tuple(window.candidates),
                    expected_symbols=tuple(sorted(expected)),
                    completed_symbols=tuple(sorted(completed)),
                    missing_symbols=tuple(sorted(expected - completed)),
                    finalization_reason=reason,
                )
            )
        return result

    def is_finalized(self, closed_at: datetime) -> bool:
        return _as_utc(closed_at) in self._finalized

    def _remember_finalized(self, key: datetime) -> None:
        self._finalized.add(key)
        self._finalized_order.append(key)
        while len(self._finalized_order) > self._finalized_capacity:
            expired = self._finalized_order.popleft()
            self._finalized.discard(expired)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
