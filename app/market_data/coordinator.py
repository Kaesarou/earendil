from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

from app.market_data.models import (
    MarketDataDecision,
    MarketDataEvent,
    MarketDataSource,
    SymbolFeedState,
)


@dataclass
class _SymbolState:
    state: SymbolFeedState = SymbolFeedState.STARTING
    last_message_received_at: datetime | None = None
    last_accepted_timestamp: datetime | None = None
    recovery_events: int = 0
    last_fallback_requested_at: datetime | None = None


class MarketDataCoordinator:
    def __init__(
        self,
        *,
        websocket_required: bool,
        symbol_silence_seconds: float,
        fallback_cooldown_seconds: float,
        duplicate_cache_size: int = 50_000,
    ) -> None:
        self.websocket_required = websocket_required
        self.symbol_silence_seconds = symbol_silence_seconds
        self.fallback_cooldown_seconds = fallback_cooldown_seconds
        self._states: dict[str, _SymbolState] = {}
        self._seen_message_ids: set[tuple[str | None, str]] = set()
        self._message_id_order: deque[tuple[str | None, str]] = deque()
        self._duplicate_cache_size = duplicate_cache_size
        self.metrics: dict[str, int] = {
            'accepted_events': 0,
            'duplicate_message_ids_dropped': 0,
            'out_of_order_events_dropped': 0,
            'symbol_fallback_count': 0,
            'symbol_recovery_count': 0,
            'blocked_symbol_count': 0,
        }

    def initialize_symbols(self, symbols: list[str], *, now: datetime) -> None:
        actual_now = _as_utc(now)
        for symbol in symbols:
            self._states[symbol.strip().upper()] = _SymbolState(
                last_message_received_at=actual_now if self.websocket_required else None
            )

    def reset_symbol(self, symbol: str, *, now: datetime | None = None) -> None:
        self._states[symbol.strip().upper()] = _SymbolState(
            last_message_received_at=(
                _as_utc(now)
                if now is not None and self.websocket_required
                else None
            )
        )

    def precheck(self, event: MarketDataEvent) -> MarketDataDecision:
        symbol = event.symbol.strip().upper()
        state = self._states.setdefault(symbol, _SymbolState())

        if event.message_id is not None:
            key = (event.connection_id, event.message_id)
            if key in self._seen_message_ids:
                self.metrics['duplicate_message_ids_dropped'] += 1
                return self._decision(False, 'duplicate_message_id', event, symbol)
            self._remember_message_id(key)

        if event.source == MarketDataSource.WEBSOCKET:
            state.last_message_received_at = _as_utc(event.received_at)

        snapshot = event.snapshot
        if snapshot is None:
            self._advance_health_without_price(state, event.source)
            return self._decision(
                False,
                'message_without_complete_quote',
                event,
                symbol,
            )

        timestamp = _as_utc(snapshot.timestamp)
        if (
            state.last_accepted_timestamp is not None
            and timestamp < state.last_accepted_timestamp
        ):
            self.metrics['out_of_order_events_dropped'] += 1
            return self._decision(
                False,
                'strict_out_of_order_timestamp',
                event,
                symbol,
            )

        if event.source == MarketDataSource.REST_CONTROL:
            return self._decision(
                False,
                'rest_control_diagnostic_only',
                event,
                symbol,
            )

        return self._decision(True, 'precheck_passed', event, symbol)

    def mark_accepted(self, event: MarketDataEvent) -> MarketDataDecision:
        symbol = event.symbol.strip().upper()
        snapshot = event.snapshot
        if snapshot is None:
            raise ValueError('Cannot accept a market-data event without a snapshot.')
        state = self._states.setdefault(symbol, _SymbolState())
        self._advance_health(state, event.source)
        state.last_accepted_timestamp = _as_utc(snapshot.timestamp)
        self.metrics['accepted_events'] += 1
        return self._decision(True, 'accepted', event, symbol)

    def decision_for(self, event: MarketDataEvent) -> MarketDataDecision:
        decision = self.precheck(event)
        return self.mark_accepted(event) if decision.accepted else decision

    def stale_symbols(
        self,
        *,
        symbols: list[str],
        now: datetime,
    ) -> list[str]:
        if not self.websocket_required:
            return []
        actual_now = _as_utc(now)
        stale: list[str] = []
        for raw_symbol in symbols:
            symbol = raw_symbol.strip().upper()
            state = self._states.setdefault(symbol, _SymbolState())
            last_message = state.last_message_received_at
            is_stale = (
                last_message is None
                or (actual_now - last_message).total_seconds()
                > self.symbol_silence_seconds
            )
            if not is_stale:
                continue
            if state.state not in {
                SymbolFeedState.REST_FALLBACK,
                SymbolFeedState.BLOCKED,
            }:
                state.state = SymbolFeedState.WS_STALE
            if self._fallback_due(state, actual_now):
                stale.append(symbol)
        return stale

    def mark_fallback_requested(self, symbols: list[str], now: datetime) -> None:
        actual_now = _as_utc(now)
        for raw_symbol in symbols:
            symbol = raw_symbol.strip().upper()
            state = self._states.setdefault(symbol, _SymbolState())
            state.last_fallback_requested_at = actual_now
            if state.state != SymbolFeedState.REST_FALLBACK:
                self.metrics['symbol_fallback_count'] += 1
            state.state = SymbolFeedState.REST_FALLBACK
            state.recovery_events = 0

    def mark_fallback_failed(self, symbols: list[str]) -> None:
        for raw_symbol in symbols:
            symbol = raw_symbol.strip().upper()
            state = self._states.setdefault(symbol, _SymbolState())
            if state.state != SymbolFeedState.BLOCKED:
                self.metrics['blocked_symbol_count'] += 1
            state.state = SymbolFeedState.BLOCKED
            state.recovery_events = 0

    def entry_allowed(self, symbol: str) -> bool:
        state = self._states.setdefault(symbol.strip().upper(), _SymbolState())
        return state.state == SymbolFeedState.WS_HEALTHY

    def state_for(self, symbol: str) -> SymbolFeedState:
        return self._states.setdefault(
            symbol.strip().upper(),
            _SymbolState(),
        ).state

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {
            symbol: {
                'state': state.state.value,
                'last_message_received_at': state.last_message_received_at,
                'last_accepted_timestamp': state.last_accepted_timestamp,
                'recovery_events': state.recovery_events,
                'last_fallback_requested_at': state.last_fallback_requested_at,
            }
            for symbol, state in sorted(self._states.items())
        }

    def _decision(
        self,
        accepted: bool,
        reason: str,
        event: MarketDataEvent,
        symbol: str,
    ) -> MarketDataDecision:
        return MarketDataDecision(
            accepted=accepted,
            reason=reason,
            event=event,
            entry_allowed=self.entry_allowed(symbol),
        )

    def _advance_health_without_price(
        self,
        state: _SymbolState,
        source: MarketDataSource,
    ) -> None:
        if source != MarketDataSource.WEBSOCKET:
            return
        if state.state in {
            SymbolFeedState.WS_STALE,
            SymbolFeedState.REST_FALLBACK,
            SymbolFeedState.BLOCKED,
        }:
            state.state = SymbolFeedState.RECOVERING
            state.recovery_events = max(1, state.recovery_events)

    def _advance_health(
        self,
        state: _SymbolState,
        source: MarketDataSource,
    ) -> None:
        if source == MarketDataSource.WEBSOCKET:
            if state.state in {
                SymbolFeedState.WS_STALE,
                SymbolFeedState.REST_FALLBACK,
                SymbolFeedState.BLOCKED,
            }:
                state.state = SymbolFeedState.RECOVERING
                state.recovery_events = 1
                return
            if state.state == SymbolFeedState.RECOVERING:
                state.recovery_events += 1
                if state.recovery_events >= 2:
                    state.state = SymbolFeedState.WS_HEALTHY
                    state.recovery_events = 0
                    self.metrics['symbol_recovery_count'] += 1
                return
            state.state = SymbolFeedState.WS_HEALTHY
            state.recovery_events = 0
            return

        if source in {
            MarketDataSource.REST_FALLBACK,
            MarketDataSource.REST_POLLING,
            MarketDataSource.PAPER,
        }:
            state.state = (
                SymbolFeedState.REST_FALLBACK
                if self.websocket_required
                and source == MarketDataSource.REST_FALLBACK
                else SymbolFeedState.WS_HEALTHY
            )

    def _fallback_due(self, state: _SymbolState, now: datetime) -> bool:
        previous = state.last_fallback_requested_at
        return (
            previous is None
            or (now - previous).total_seconds() >= self.fallback_cooldown_seconds
        )

    def _remember_message_id(self, key: tuple[str | None, str]) -> None:
        self._seen_message_ids.add(key)
        self._message_id_order.append(key)
        while len(self._message_id_order) > self._duplicate_cache_size:
            expired = self._message_id_order.popleft()
            self._seen_message_ids.discard(expired)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
