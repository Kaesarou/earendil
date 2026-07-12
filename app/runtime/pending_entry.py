import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum

from app.execution.candidate_economics import EvaluatedTradeCandidate
from app.execution.trade_candidate import TradeCandidate
from app.market.models import Candle, MarketSnapshot
from app.strategies.entry_confirmation import EntryConfirmationConfig, EntryConfirmationEvaluator
from app.strategies.signals import Signal
from app.utils.commons import normalize_symbol


class PendingEntryState(StrEnum):
    WAITING = 'waiting'
    RETEST_DETECTED = 'retest_detected'
    CONFIRMED = 'confirmed'
    INVALIDATED = 'invalidated'
    EXPIRED = 'expired'


@dataclass(frozen=True)
class PendingEntry:
    symbol: str
    side: str
    session_key: str
    detected_at: datetime
    detected_candle_time: datetime
    initial_reference_price: float
    breakout_or_breakdown_level: float
    initial_score: float
    initial_runway_score: float
    initial_penalty: float
    expires_after_candles: int
    observed_candles: int = 0
    state: PendingEntryState = PendingEntryState.WAITING
    consecutive_closes: int = 0
    retest_extreme_price: float | None = None
    structural_invalidation_price: float | None = None
    confirmation_type: str | None = None

    @property
    def key(self) -> str:
        return f'{self.symbol}:{self.side}:{self.session_key}'

    @property
    def setup_key(self) -> tuple[str, str, str, float]:
        return (
            self.symbol,
            self.side,
            self.session_key,
            round(self.breakout_or_breakdown_level, 8),
        )


@dataclass(frozen=True)
class PendingEntryEvent:
    event_type: str
    pending: PendingEntry
    reason: str


@dataclass(frozen=True)
class PendingEntryObservation:
    events: tuple[PendingEntryEvent, ...] = ()
    confirmed_pending: PendingEntry | None = None
    confirmation_signal: Signal | None = None


class PendingEntryManager:
    def __init__(self, evaluator: EntryConfirmationEvaluator | None = None):
        self.evaluator = evaluator or EntryConfirmationEvaluator()
        self._entries: dict[str, PendingEntry] = {}
        self._expired_setups: set[tuple[str, str, str, float]] = set()

    def snapshot(self) -> list[PendingEntry]:
        return list(self._entries.values())

    def get(self, key: str) -> PendingEntry | None:
        return self._entries.get(key)

    def register(
        self,
        *,
        evaluated_candidate: EvaluatedTradeCandidate,
        max_candles: int,
        detected_at: datetime | None = None,
    ) -> tuple[PendingEntryEvent, ...]:
        candidate = evaluated_candidate.candidate
        side = candidate.signal.action.strip().upper()
        if side not in {'BUY', 'SELL'}:
            return ()
        symbol = normalize_symbol(candidate.symbol)
        session_key = candidate.session_key
        level = self._breakout_level(candidate)
        if level is None or level <= 0 or not session_key:
            return ()

        setup_key = self._setup_key(symbol, side, session_key, level)
        if setup_key in self._expired_setups:
            return ()

        events: list[PendingEntryEvent] = []
        for existing in list(self._entries.values()):
            if existing.symbol == symbol and existing.side != side:
                invalidated = replace(existing, state=PendingEntryState.INVALIDATED)
                self._entries.pop(existing.key, None)
                events.append(
                    PendingEntryEvent(
                        'pending_entry_invalidated',
                        invalidated,
                        'opposite_signal',
                    )
                )

        key = f'{symbol}:{side}:{session_key}'
        analysis = evaluated_candidate.tp_feasibility
        runway = analysis.raw_runway_score if analysis is not None else 0.0
        penalty = analysis.raw_tp_feasibility_penalty if analysis is not None else 0.0
        existing = self._entries.get(key)
        if existing is not None:
            updated = replace(
                existing,
                initial_score=candidate.score,
                initial_runway_score=runway,
                initial_penalty=penalty,
                state=(
                    PendingEntryState.WAITING
                    if existing.state == PendingEntryState.CONFIRMED
                    else existing.state
                ),
            )
            self._entries[key] = updated
            events.append(
                PendingEntryEvent(
                    'pending_entry_updated',
                    updated,
                    'same_signal_refreshed_without_extending_expiry',
                )
            )
            return tuple(events)

        pending = PendingEntry(
            symbol=symbol,
            side=side,
            session_key=session_key,
            detected_at=detected_at or datetime.now(timezone.utc),
            detected_candle_time=candidate.candle.closed_at,
            initial_reference_price=candidate.snapshot.last,
            breakout_or_breakdown_level=level,
            initial_score=candidate.score,
            initial_runway_score=runway,
            initial_penalty=penalty,
            expires_after_candles=max(1, max_candles),
        )
        self._entries[pending.key] = pending
        events.append(
            PendingEntryEvent(
                'pending_entry_registered',
                pending,
                evaluated_candidate.readiness_reason or 'wait_confirmation',
            )
        )
        return tuple(events)

    def observe(
        self,
        *,
        symbol: str,
        candle: Candle,
        snapshot: MarketSnapshot,
        signal: Signal,
        session_key: str | None,
        session_tradable: bool,
        spread_percent: float,
        config: EntryConfirmationConfig,
        cooldown_active: bool = False,
        max_spread_percent: float | None = None,
    ) -> PendingEntryObservation:
        normalized_symbol = normalize_symbol(symbol)
        events: list[PendingEntryEvent] = []
        confirmed: PendingEntry | None = None
        confirmation_signal: Signal | None = None

        for stored_pending in list(self._entries.values()):
            if stored_pending.symbol != normalized_symbol:
                continue
            pending = stored_pending
            if pending.state == PendingEntryState.CONFIRMED:
                pending = replace(
                    pending,
                    state=PendingEntryState.WAITING,
                    confirmation_type=None,
                )
                self._entries[pending.key] = pending
            if not session_tradable or session_key != pending.session_key:
                events.append(self._invalidate(pending, 'session_not_tradable'))
                continue
            if cooldown_active:
                events.append(self._invalidate(pending, 'cooldown_registered'))
                continue
            if not self._market_data_valid(snapshot=snapshot, candle=candle):
                events.append(self._invalidate(pending, 'invalid_market_data'))
                continue
            if (
                max_spread_percent is not None
                and max_spread_percent > 0
                and spread_percent > max_spread_percent
            ):
                events.append(self._invalidate(pending, 'spread_too_high'))
                continue

            observed_candles = pending.observed_candles + 1
            decision = self.evaluator.evaluate(
                side=pending.side,
                breakout_level=pending.breakout_or_breakdown_level,
                previous_state=pending.state.value,
                previous_consecutive_closes=pending.consecutive_closes,
                previous_retest_extreme_price=pending.retest_extreme_price,
                previous_structure_extreme_price=pending.structural_invalidation_price,
                candle=candle,
                signal=signal,
                spread_percent=spread_percent,
                config=config,
            )
            if decision.state == PendingEntryState.INVALIDATED.value:
                events.append(self._invalidate(pending, decision.reason))
                continue

            next_state = PendingEntryState(decision.state)
            updated = replace(
                pending,
                observed_candles=observed_candles,
                state=next_state,
                consecutive_closes=decision.consecutive_closes,
                retest_extreme_price=decision.retest_extreme_price,
                structural_invalidation_price=decision.structural_invalidation_price,
                confirmation_type=decision.confirmation_type,
            )
            if next_state == PendingEntryState.CONFIRMED:
                self._entries[pending.key] = updated
                events.append(
                    PendingEntryEvent(
                        'pending_entry_confirmed',
                        updated,
                        decision.reason,
                    )
                )
                confirmed = updated
                confirmation_signal = self._confirmation_signal(
                    signal=signal,
                    pending=updated,
                )
                continue
            if observed_candles >= pending.expires_after_candles:
                expired = replace(updated, state=PendingEntryState.EXPIRED)
                self._entries.pop(pending.key, None)
                self._expired_setups.add(expired.setup_key)
                events.append(
                    PendingEntryEvent(
                        'pending_entry_expired',
                        expired,
                        'max_candles_reached',
                    )
                )
                continue
            self._entries[pending.key] = updated
            if next_state == PendingEntryState.RETEST_DETECTED:
                events.append(
                    PendingEntryEvent(
                        'pending_entry_retest_detected',
                        updated,
                        decision.reason,
                    )
                )

        return PendingEntryObservation(tuple(events), confirmed, confirmation_signal)

    def mark_waiting_after_recalculation(self, pending_key: str) -> None:
        pending = self._entries.get(pending_key)
        if pending is not None:
            self._entries[pending_key] = replace(
                pending,
                state=PendingEntryState.WAITING,
                confirmation_type=None,
            )

    def remove(self, pending_key: str) -> PendingEntry | None:
        return self._entries.pop(pending_key, None)

    def invalidate_session(self, session_key: str) -> tuple[PendingEntryEvent, ...]:
        events = tuple(
            self._invalidate(pending, 'session_closed')
            for pending in list(self._entries.values())
            if pending.session_key == session_key
        )
        self._expired_setups = {
            setup_key
            for setup_key in self._expired_setups
            if setup_key[2] != session_key
        }
        return events

    def invalidate_symbol(
        self,
        symbol: str,
        reason: str,
    ) -> tuple[PendingEntryEvent, ...]:
        normalized_symbol = normalize_symbol(symbol)
        return tuple(
            self._invalidate(pending, reason)
            for pending in list(self._entries.values())
            if pending.symbol == normalized_symbol
        )

    def _invalidate(self, pending: PendingEntry, reason: str) -> PendingEntryEvent:
        invalidated = replace(pending, state=PendingEntryState.INVALIDATED)
        self._entries.pop(pending.key, None)
        return PendingEntryEvent('pending_entry_invalidated', invalidated, reason)

    def _confirmation_signal(self, *, signal: Signal, pending: PendingEntry) -> Signal:
        metadata = dict(signal.metadata or {})
        metadata.update(
            {
                'entry_origin': 'pending_confirmation',
                'pending_entry_id': pending.key,
                'confirmation_type': pending.confirmation_type,
                'structural_invalidation_price': pending.structural_invalidation_price,
                'pending_observed_candles': pending.observed_candles,
            }
        )
        return replace(signal, metadata=metadata)

    def _breakout_level(self, candidate: TradeCandidate) -> float | None:
        metadata = candidate.signal.metadata or {}
        key = 'range_high' if candidate.signal.action == 'BUY' else 'range_low'
        raw = metadata.get(key)
        try:
            return float(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    def _setup_key(
        self,
        symbol: str,
        side: str,
        session_key: str,
        level: float,
    ) -> tuple[str, str, str, float]:
        return (symbol, side, session_key, round(level, 8))

    def _market_data_valid(
        self,
        *,
        snapshot: MarketSnapshot,
        candle: Candle,
    ) -> bool:
        values = (
            snapshot.bid,
            snapshot.ask,
            snapshot.last,
            candle.open,
            candle.high,
            candle.low,
            candle.close,
        )
        return all(
            isinstance(value, (int, float))
            and math.isfinite(float(value))
            and float(value) > 0
            for value in values
        )