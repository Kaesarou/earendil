from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Any, Callable

from app.brokers.base import BrokerClient
from app.execution.position_tracker import (
    PositionCloseSignal,
    PositionTracker,
    TrackedPosition,
)
from app.execution.trade_executor import TradeExecutor
from app.journal.jsonl_journal import JsonlJournal
from app.market.models import MarketSnapshot
from app.market_data.contracts import RestMarketDataClient
from app.market_data.coordinator import MarketDataCoordinator
from app.persistence.position_store import PositionStore
from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.risk_manager import RiskManager
from app.runtime.broker_queries import get_fresh_position_open_states
from app.runtime.broker_task_runner import BrokerTaskCompletion, BrokerTaskRunner
from app.runtime.position_lifecycle import (
    register_trade_cooldown_for_closed_position,
    register_trade_cooldown_for_missing_position,
)
from app.runtime.position_reconciliation_state import (
    PositionReconciliationOutcome,
    PositionReconciliationTracker,
)
from app.runtime.trading_session_window import FORCE_CLOSE_BEFORE_SESSION_END


logger = logging.getLogger(__name__)
BrokerAuthorizationErrorChecker = Callable[[Exception], bool]


@dataclass(frozen=True)
class _ReconciliationContext:
    positions: tuple[TrackedPosition, ...]
    requested_at: datetime


@dataclass(frozen=True)
class _RestContext:
    symbols: tuple[str, ...]
    requested_at: datetime


@dataclass(frozen=True)
class _CloseContext:
    signal: PositionCloseSignal
    source: str
    session_decision: Any = None


class AsyncBrokerOperationsCoordinator:
    def __init__(
        self,
        *,
        runner: BrokerTaskRunner,
        execution_broker: BrokerClient,
        rest_market_data: RestMarketDataClient,
        executor: TradeExecutor,
        position_tracker: PositionTracker,
        risk_manager: RiskManager,
        position_store: PositionStore,
        cooldown_store: TradeCooldownStore,
        trade_journal: JsonlJournal,
        market_data_coordinator: MarketDataCoordinator,
        is_broker_authorization_error: BrokerAuthorizationErrorChecker,
        reconciliation_grace_seconds: float = 30.0,
        reconciliation_required_misses: int = 3,
        reconciliation_miss_interval_seconds: float = 10.0,
        rest_control_anomaly_percent: float = 0.25,
    ) -> None:
        self.runner = runner
        self.execution_broker = execution_broker
        self.rest_market_data = rest_market_data
        self.executor = executor
        self.position_tracker = position_tracker
        self.risk_manager = risk_manager
        self.position_store = position_store
        self.cooldown_store = cooldown_store
        self.trade_journal = trade_journal
        self.market_data_coordinator = market_data_coordinator
        self.is_broker_authorization_error = is_broker_authorization_error
        self.rest_control_anomaly_percent = max(0.0, rest_control_anomaly_percent)
        self.reconciliation = PositionReconciliationTracker(
            grace_seconds=reconciliation_grace_seconds,
            required_misses=reconciliation_required_misses,
            minimum_miss_interval_seconds=(
                reconciliation_miss_interval_seconds
            ),
        )
        self._pending_close_ids: set[str] = set()

    def schedule_reconciliation(self, *, now: datetime) -> bool:
        if self.runner.has_pending_kind('position_reconciliation'):
            return False
        positions = tuple(self.position_tracker.open_positions_snapshot())
        if not positions:
            return False
        context = _ReconciliationContext(
            positions=positions,
            requested_at=_as_utc(now),
        )
        position_ids = [position.position_id for position in positions]
        self.runner.submit(
            kind='position_reconciliation',
            context=context,
            operation=lambda ids=position_ids: get_fresh_position_open_states(
                self.execution_broker,
                ids,
            ),
        )
        return True

    def schedule_rest_control(
        self,
        *,
        symbols: list[str],
        now: datetime,
    ) -> bool:
        if not symbols or self.runner.has_pending_kind('rest_control'):
            return False
        context = _RestContext(tuple(symbols), _as_utc(now))
        self.runner.submit(
            kind='rest_control',
            context=context,
            operation=lambda requested=list(symbols): (
                self.rest_market_data.get_market_snapshots(requested)
            ),
        )
        return True

    def schedule_position_fallback(
        self,
        *,
        symbols: list[str],
        now: datetime,
    ) -> bool:
        if not symbols or self.runner.has_pending_kind('position_fallback'):
            return False
        context = _RestContext(tuple(symbols), _as_utc(now))
        self.runner.submit(
            kind='position_fallback',
            context=context,
            operation=lambda requested=list(symbols): (
                self.rest_market_data.get_market_snapshots(requested)
            ),
        )
        return True

    def on_snapshot(
        self,
        *,
        snapshot: MarketSnapshot,
        session_decision: Any = None,
        source: str = 'websocket',
    ) -> None:
        close_signals = self.position_tracker.evaluate_snapshot(snapshot)
        self._record_managed_stop_updates(snapshot)
        for close_signal in close_signals:
            self.submit_close(
                signal=close_signal,
                source=f'{source}_position_guard',
            )
        if session_decision is None or not getattr(
            session_decision,
            'force_close_required',
            False,
        ):
            return
        for position in self.position_tracker.open_positions_snapshot():
            if position.symbol != snapshot.symbol:
                continue
            self.submit_close(
                signal=PositionCloseSignal(
                    position_id=position.position_id,
                    symbol=position.symbol,
                    side=position.side,
                    exit_price=snapshot.last,
                    reason=FORCE_CLOSE_BEFORE_SESSION_END,
                    detected_at=snapshot.timestamp,
                    metadata={
                        'session_decision': getattr(
                            session_decision,
                            'reason',
                            None,
                        ),
                        'time_until_session_end_minutes': getattr(
                            session_decision,
                            'time_until_session_end_minutes',
                            None,
                        ),
                    },
                ),
                source='session_force_close',
                session_decision=session_decision,
            )

    def submit_close(
        self,
        *,
        signal: PositionCloseSignal,
        source: str,
        session_decision: Any = None,
    ) -> bool:
        if signal.position_id in self._pending_close_ids:
            return False
        tracked_ids = {
            position.position_id
            for position in self.position_tracker.open_positions_snapshot()
        }
        if signal.position_id not in tracked_ids:
            return False
        self._pending_close_ids.add(signal.position_id)
        context = _CloseContext(
            signal=signal,
            source=source,
            session_decision=session_decision,
        )
        self.trade_journal.write(
            'position_close_pending',
            {
                'source': source,
                'symbol': signal.symbol,
                'position_id': signal.position_id,
                'close_signal': signal,
            },
        )
        self.runner.submit(
            kind='close_position',
            context=context,
            operation=lambda position_id=signal.position_id: (
                self.executor.close(position_id)
            ),
        )
        return True

    def handle_completion(
        self,
        completion: BrokerTaskCompletion,
        *,
        now: datetime,
        latest_snapshots: dict[str, MarketSnapshot],
    ) -> bool:
        if completion.kind == 'position_reconciliation':
            self._handle_reconciliation(completion, now=_as_utc(now))
            return True
        if completion.kind == 'rest_control':
            self._handle_rest_control(
                completion,
                latest_snapshots=latest_snapshots,
                now=_as_utc(now),
            )
            return True
        if completion.kind == 'position_fallback':
            self._handle_position_fallback(completion, now=_as_utc(now))
            return True
        if completion.kind == 'close_position':
            self._handle_close(completion)
            return True
        return False

    def diagnostics(self) -> dict[str, Any]:
        return {
            'pending_close_position_ids': sorted(self._pending_close_ids),
            'reconciliation_evidence': self.reconciliation.snapshot(),
        }

    def _handle_reconciliation(
        self,
        completion: BrokerTaskCompletion,
        *,
        now: datetime,
    ) -> None:
        context = completion.context
        if not isinstance(context, _ReconciliationContext):
            return
        if completion.error is not None:
            if self.is_broker_authorization_error(completion.error):
                raise completion.error
            self.trade_journal.write(
                'position_reconciliation_warning',
                {
                    'position_count': len(context.positions),
                    'message': str(completion.error),
                },
            )
            return
        states = completion.value
        if not isinstance(states, dict):
            self.trade_journal.write(
                'position_reconciliation_warning',
                {
                    'position_count': len(context.positions),
                    'message': 'invalid_position_state_payload',
                },
            )
            return
        current_by_id = {
            position.position_id: position
            for position in self.position_tracker.open_positions_snapshot()
        }
        positions = [
            current_by_id[position.position_id]
            for position in context.positions
            if position.position_id in current_by_id
        ]
        outcome = self.reconciliation.observe(
            positions=positions,
            open_states={str(key): bool(value) for key, value in states.items()},
            observed_at=now,
        )
        self._write_reconciliation_outcome(outcome)
        for position in outcome.confirmed_closed:
            self._apply_reconciled_close(position, closed_at=now)

    def _write_reconciliation_outcome(
        self,
        outcome: PositionReconciliationOutcome,
    ) -> None:
        for position in outcome.newly_suspect:
            evidence = self.reconciliation.evidence_for(position.position_id)
            self.trade_journal.write(
                'position_reconciliation_suspect',
                {
                    'position': position,
                    'evidence': evidence,
                    'risk_reserved': True,
                },
            )
        for position in outcome.still_suspect:
            evidence = self.reconciliation.evidence_for(position.position_id)
            self.trade_journal.write(
                'position_reconciliation_suspect_updated',
                {'position': position, 'evidence': evidence},
            )
        for position in outcome.recovered:
            self.trade_journal.write(
                'position_reconciliation_recovered',
                {'position': position},
            )
        if outcome.grace_ignored:
            self.trade_journal.write(
                'position_reconciliation_grace',
                {
                    'position_ids': [
                        position.position_id
                        for position in outcome.grace_ignored
                    ],
                    'count': len(outcome.grace_ignored),
                },
            )
        if outcome.missing_states:
            self.trade_journal.write(
                'position_reconciliation_warning',
                {
                    'position_ids': [
                        position.position_id
                        for position in outcome.missing_states
                    ],
                    'message': 'broker_position_state_missing',
                },
            )

    def _apply_reconciled_close(
        self,
        position: TrackedPosition,
        *,
        closed_at: datetime,
    ) -> None:
        removed = self.position_tracker.remove_position(position.position_id)
        if removed is None:
            return
        self._pending_close_ids.discard(position.position_id)
        closed_session_key = self.risk_manager.record_close_position(
            removed.symbol
        )
        try:
            self.position_store.delete_open_position(removed.position_id)
        except Exception as exc:  # noqa: BLE001
            self.trade_journal.write(
                'position_persistence_error',
                {
                    'symbol': removed.symbol,
                    'position_id': removed.position_id,
                    'message': str(exc),
                },
            )
        register_trade_cooldown_for_missing_position(
            position=removed,
            closed_at=closed_at,
            risk_manager=self.risk_manager,
            cooldown_store=self.cooldown_store,
            trade_journal=self.trade_journal,
            session_key=closed_session_key,
        )
        self.trade_journal.write(
            'position_reconciled_closed',
            {
                'source': 'runtime_broker_reconciliation_confirmed',
                'position': removed,
                'closed_at': closed_at,
                'confirmation_policy': 'three_fresh_absences_after_grace',
            },
        )

    def _handle_rest_control(
        self,
        completion: BrokerTaskCompletion,
        *,
        latest_snapshots: dict[str, MarketSnapshot],
        now: datetime,
    ) -> None:
        context = completion.context
        if not isinstance(context, _RestContext):
            return
        if completion.error is not None:
            self.trade_journal.write(
                'rest_control_error',
                {
                    'symbols': list(context.symbols),
                    'message': str(completion.error),
                },
            )
            return
        snapshots = completion.value
        if not isinstance(snapshots, dict):
            return
        deltas: list[float] = []
        anomalies: list[dict[str, Any]] = []
        for symbol, rest_snapshot in snapshots.items():
            websocket_snapshot = latest_snapshots.get(symbol)
            if websocket_snapshot is None or websocket_snapshot.last == 0:
                continue
            delta_percent = abs(
                (rest_snapshot.last - websocket_snapshot.last)
                / websocket_snapshot.last
                * 100
            )
            deltas.append(delta_percent)
            if delta_percent >= self.rest_control_anomaly_percent:
                anomalies.append(
                    {
                        'symbol': symbol,
                        'delta_percent': round(delta_percent, 6),
                        'rest_last': rest_snapshot.last,
                        'websocket_last': websocket_snapshot.last,
                    }
                )
        sorted_deltas = sorted(deltas)
        self.trade_journal.write(
            'rest_control_completed',
            {
                'requested_symbol_count': len(context.symbols),
                'received_symbol_count': len(snapshots),
                'compared_symbol_count': len(deltas),
                'missing_symbol_count': max(
                    0,
                    len(context.symbols) - len(snapshots),
                ),
                'median_delta_percent': (
                    round(median(deltas), 6) if deltas else None
                ),
                'p95_delta_percent': _percentile(sorted_deltas, 0.95),
                'max_delta_percent': (
                    round(max(deltas), 6) if deltas else None
                ),
                'anomaly_count': len(anomalies),
                'anomalies': anomalies,
                'requested_at': context.requested_at,
                'completed_at': now,
            },
        )

    def _handle_position_fallback(
        self,
        completion: BrokerTaskCompletion,
        *,
        now: datetime,
    ) -> None:
        context = completion.context
        if not isinstance(context, _RestContext):
            return
        symbols = list(context.symbols)
        if completion.error is not None:
            self.market_data_coordinator.mark_fallback_failed(symbols)
            self.trade_journal.write(
                'rest_position_fallback_error',
                {'symbols': symbols, 'message': str(completion.error)},
            )
            return
        snapshots = completion.value
        if not isinstance(snapshots, dict):
            snapshots = {}
        received = list(snapshots)
        if received:
            self.market_data_coordinator.mark_fallback_succeeded(received)
        missing = [symbol for symbol in symbols if symbol not in snapshots]
        if missing:
            self.market_data_coordinator.mark_fallback_failed(missing)
        self.trade_journal.write(
            'rest_position_fallback_completed',
            {
                'requested_symbols': symbols,
                'received_symbols': received,
                'missing_symbols': missing,
                'requested_at': context.requested_at,
                'completed_at': now,
            },
        )
        for snapshot in snapshots.values():
            self.on_snapshot(
                snapshot=snapshot,
                session_decision=None,
                source='rest_fallback',
            )

    def _handle_close(self, completion: BrokerTaskCompletion) -> None:
        context = completion.context
        if not isinstance(context, _CloseContext):
            return
        signal = context.signal
        self._pending_close_ids.discard(signal.position_id)
        if completion.error is not None:
            if self.is_broker_authorization_error(completion.error):
                raise completion.error
            self.trade_journal.write(
                'position_close_error',
                {
                    'source': context.source,
                    'symbol': signal.symbol,
                    'close_signal': signal,
                    'message': str(completion.error),
                    'session_decision': context.session_decision,
                },
            )
            return
        closed_position = self.position_tracker.record_closed_position(signal)
        if closed_position is None:
            return
        closed_session_key = self.risk_manager.record_close_position(signal.symbol)
        try:
            self.position_store.delete_open_position(signal.position_id)
        except Exception as exc:  # noqa: BLE001
            self.trade_journal.write(
                'position_persistence_error',
                {
                    'symbol': signal.symbol,
                    'position_id': signal.position_id,
                    'message': str(exc),
                },
            )
        register_trade_cooldown_for_closed_position(
            closed_position=closed_position,
            risk_manager=self.risk_manager,
            cooldown_store=self.cooldown_store,
            trade_journal=self.trade_journal,
            session_key=closed_session_key,
        )
        self.reconciliation.clear(signal.position_id)
        self.trade_journal.write(
            'position_closed',
            {
                'source': context.source,
                'symbol': signal.symbol,
                'close_signal': signal,
                'closed_position': closed_position,
                'session_decision': context.session_decision,
            },
        )

    def _record_managed_stop_updates(self, snapshot: MarketSnapshot) -> None:
        for update in self.position_tracker.consume_managed_stop_updates():
            position = update.position
            self.trade_journal.write(
                'managed_stop_updated',
                {
                    'symbol': position.symbol,
                    'position_id': position.position_id,
                    'side': position.side,
                    'protection_type': position.managed_stop_protection_type,
                    'previous_stop_loss': update.previous_position.stop_loss,
                    'new_stop_loss': position.stop_loss,
                    'observed_at': update.observed_at,
                    'snapshot': snapshot,
                    'position': position,
                    'metadata': position.last_stop_update_metadata,
                },
            )
            try:
                self.position_store.save_open_position(position)
            except Exception as exc:  # noqa: BLE001
                self.trade_journal.write(
                    'position_persistence_error',
                    {
                        'symbol': position.symbol,
                        'position_id': position.position_id,
                        'stage': 'managed_stop_update',
                        'message': str(exc),
                    },
                )


def _percentile(sorted_values: list[float], fraction: float) -> float | None:
    if not sorted_values:
        return None
    index = min(
        len(sorted_values) - 1,
        max(0, round((len(sorted_values) - 1) * fraction)),
    )
    return round(sorted_values[index], 6)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
