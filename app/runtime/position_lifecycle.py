import logging
from collections.abc import Callable
from datetime import datetime, timezone

from app.brokers.base import BrokerClient
from app.execution.position_tracker import ClosedPosition, PositionTracker, TrackedPosition
from app.execution.trade_executor import TradeExecutor
from app.journal.jsonl_journal import JsonlJournal
from app.market.models import MarketSnapshot
from app.persistence.position_store import PositionStore
from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.risk_manager import RiskManager
from app.risk.trade_cooldown import CloseReason, build_trade_cooldown_entry

logger = logging.getLogger(__name__)

BrokerAuthorizationErrorChecker = Callable[[Exception], bool]


def _cooldown_payload(
    *,
    entry,
    cooldown_config,
) -> dict:
    symbol_lock_expires_at = None
    if entry.close_reason == CloseReason.STOP_LOSS:
        symbol_lock_expires_at = entry.symbol_lock_expires_at(cooldown_config)
    return {
        'entry': entry,
        'session_key': entry.session_key,
        'lock_scope': entry.lock_scope,
        'blocked_sides': list(entry.blocked_sides),
        'registered_at': entry.registered_at,
        'expires_at': entry.expires_at,
        'symbol_lock_expires_at': symbol_lock_expires_at,
    }


def register_trade_cooldown_for_closed_position(
    *,
    closed_position: ClosedPosition | None,
    risk_manager: RiskManager,
    cooldown_store: TradeCooldownStore,
    trade_journal: JsonlJournal,
    session_key: str | None = None,
) -> None:
    if closed_position is None:
        return

    cooldown_config = risk_manager.risk_profile_for(closed_position.symbol).trade_cooldown
    if not cooldown_config.enabled:
        return

    entry = build_trade_cooldown_entry(
        symbol=closed_position.symbol,
        side=closed_position.side,
        config=cooldown_config,
        raw_close_reason=closed_position.close_reason,
        closed_at=closed_position.closed_at,
        position_id=closed_position.position_id,
        gross_pnl=closed_position.gross_pnl,
        gross_pnl_percent=closed_position.gross_pnl_percent,
        session_key=session_key,
    )
    saved_entry = cooldown_store.save_or_extend(entry)

    trade_journal.write(
        'trade_cooldown_registered',
        {
            'source': 'bot_close',
            **_cooldown_payload(
                entry=saved_entry,
                cooldown_config=cooldown_config,
            ),
            'closed_position': closed_position,
        },
    )
    logger.info(
        'Trade cooldown registered | source=bot_close | symbol=%s | side=%s | '
        'reason=%s | lock_scope=%s | expires_at=%s',
        saved_entry.symbol,
        saved_entry.side,
        saved_entry.close_reason.value,
        saved_entry.lock_scope,
        saved_entry.expires_at.isoformat(),
    )


def register_trade_cooldown_for_missing_position(
    *,
    position: TrackedPosition,
    closed_at: datetime,
    risk_manager: RiskManager,
    cooldown_store: TradeCooldownStore,
    trade_journal: JsonlJournal,
    session_key: str | None = None,
) -> None:
    cooldown_config = risk_manager.risk_profile_for(position.symbol).trade_cooldown
    if not cooldown_config.enabled:
        return

    entry = build_trade_cooldown_entry(
        symbol=position.symbol,
        side=position.side,
        config=cooldown_config,
        raw_close_reason='broker_position_missing',
        closed_at=closed_at,
        position_id=position.position_id,
        session_key=session_key,
    )
    saved_entry = cooldown_store.save_or_extend(entry)

    trade_journal.write(
        'trade_cooldown_registered',
        {
            'source': 'broker_reconciliation',
            **_cooldown_payload(
                entry=saved_entry,
                cooldown_config=cooldown_config,
            ),
            'position': position,
        },
    )
    logger.info(
        'Trade cooldown registered | source=broker_reconciliation | symbol=%s | '
        'side=%s | reason=%s | lock_scope=%s | expires_at=%s',
        saved_entry.symbol,
        saved_entry.side,
        saved_entry.close_reason.value,
        saved_entry.lock_scope,
        saved_entry.expires_at.isoformat(),
    )


def close_positions_triggered_by_snapshot(
    *,
    symbol: str,
    snapshot: MarketSnapshot,
    executor: TradeExecutor,
    position_tracker: PositionTracker,
    risk_manager: RiskManager,
    trade_journal: JsonlJournal,
    is_broker_authorization_error: BrokerAuthorizationErrorChecker,
    position_store: PositionStore | None = None,
    cooldown_store: TradeCooldownStore | None = None,
) -> None:
    close_signals = position_tracker.evaluate_snapshot(snapshot)
    for close_signal in close_signals:
        try:
            executor.close(close_signal.position_id)
            closed_position = position_tracker.record_closed_position(close_signal)
            closed_session_key = risk_manager.record_close_position(close_signal.symbol)

            if position_store is not None:
                try:
                    position_store.delete_open_position(close_signal.position_id)
                except Exception as exc:
                    logger.exception(
                        'Position persistence delete error | position_id=%s | error=%s',
                        close_signal.position_id,
                        exc,
                    )
                    trade_journal.write(
                        'position_persistence_error',
                        {
                            'symbol': symbol,
                            'position_id': close_signal.position_id,
                            'message': str(exc),
                        },
                    )

            if cooldown_store is not None:
                register_trade_cooldown_for_closed_position(
                    closed_position=closed_position,
                    risk_manager=risk_manager,
                    cooldown_store=cooldown_store,
                    trade_journal=trade_journal,
                    session_key=closed_session_key,
                )

            trade_journal.write(
                'position_closed',
                {
                    'symbol': symbol,
                    'close_signal': close_signal,
                    'closed_position': closed_position,
                },
            )

        except Exception as exc:
            if is_broker_authorization_error(exc):
                raise

            logger.exception(
                'Position close error | symbol=%s | position_id=%s | reason=%s | '
                'error=%s',
                symbol,
                close_signal.position_id,
                close_signal.reason,
                exc,
            )
            trade_journal.write(
                'position_close_error',
                {
                    'symbol': symbol,
                    'close_signal': close_signal,
                    'message': str(exc),
                },
            )


def reconcile_externally_closed_positions(
    *,
    broker: BrokerClient,
    position_tracker: PositionTracker,
    risk_manager: RiskManager,
    position_store: PositionStore,
    cooldown_store: TradeCooldownStore,
    trade_journal: JsonlJournal,
    is_broker_authorization_error: BrokerAuthorizationErrorChecker,
) -> None:
    for position in position_tracker.open_positions_snapshot():
        try:
            if broker.is_position_open(position.position_id):
                continue
        except Exception as exc:
            if is_broker_authorization_error(exc):
                raise

            logger.exception(
                'Position reconciliation check failed | position_id=%s | '
                'symbol=%s | error=%s',
                position.position_id,
                position.symbol,
                exc,
            )
            trade_journal.write(
                'position_reconciliation_warning',
                {'position': position, 'message': str(exc)},
            )
            continue

        removed_position = position_tracker.remove_position(position.position_id)
        if removed_position is None:
            continue

        closed_at = datetime.now(timezone.utc)
        closed_session_key = risk_manager.record_close_position(removed_position.symbol)

        try:
            position_store.delete_open_position(removed_position.position_id)
        except Exception as exc:
            logger.exception(
                'Position persistence delete error | position_id=%s | error=%s',
                removed_position.position_id,
                exc,
            )
            trade_journal.write(
                'position_persistence_error',
                {
                    'symbol': removed_position.symbol,
                    'position_id': removed_position.position_id,
                    'message': str(exc),
                },
            )

        register_trade_cooldown_for_missing_position(
            position=removed_position,
            closed_at=closed_at,
            risk_manager=risk_manager,
            cooldown_store=cooldown_store,
            trade_journal=trade_journal,
            session_key=closed_session_key,
        )

        logger.warning(
            'Tracked position no longer open at broker | position_id=%s | '
            'symbol=%s | side=%s',
            removed_position.position_id,
            removed_position.symbol,
            removed_position.side,
        )
        trade_journal.write(
            'position_reconciled_closed',
            {
                'source': 'runtime_broker_reconciliation',
                'position': removed_position,
                'closed_at': closed_at,
            },
        )


def restore_persisted_positions(
    position_store: PositionStore,
    position_tracker: PositionTracker,
    risk_manager: RiskManager,
    broker: BrokerClient,
    trade_journal: JsonlJournal,
    is_broker_authorization_error: BrokerAuthorizationErrorChecker,
    cooldown_store: TradeCooldownStore | None = None,
) -> None:
    restored_positions = position_store.load_open_positions()

    if not restored_positions:
        logger.info('No persisted open positions to restore')
        return

    logger.warning(
        'Restoring persisted open positions | count=%s',
        len(restored_positions),
    )

    for position in restored_positions:
        try:
            if not broker.is_position_open(position.position_id):
                closed_at = datetime.now(timezone.utc)
                logger.warning(
                    'Persisted position no longer open at broker | position_id=%s | '
                    'symbol=%s',
                    position.position_id,
                    position.symbol,
                )
                position_store.delete_open_position(position.position_id)

                if cooldown_store is not None:
                    register_trade_cooldown_for_missing_position(
                        position=position,
                        closed_at=closed_at,
                        risk_manager=risk_manager,
                        cooldown_store=cooldown_store,
                        trade_journal=trade_journal,
                    )

                trade_journal.write(
                    'position_reconciled_closed',
                    {
                        'source': 'startup_broker_reconciliation',
                        'position': position,
                        'closed_at': closed_at,
                    },
                )
                continue

        except Exception as exc:
            if is_broker_authorization_error(exc):
                logger.critical(
                    'Broker authorization failed during position reconciliation. '
                    'Stopping before restoring unverified positions | position_id=%s | '
                    'symbol=%s | error=%s',
                    position.position_id,
                    position.symbol,
                    exc,
                )
                trade_journal.write(
                    'broker_authorization_error',
                    {
                        'stage': 'position_reconciliation',
                        'position': position,
                        'message': str(exc),
                    },
                )
                raise

            logger.exception(
                'Position reconciliation check failed | position_id=%s | '
                'symbol=%s | error=%s',
                position.position_id,
                position.symbol,
                exc,
            )
            trade_journal.write(
                'position_reconciliation_warning',
                {'position': position, 'message': str(exc)},
            )

        position_tracker.restore_open_position(position)
        risk_manager.restore_open_position(position.symbol)

        if hasattr(broker, 'remember_position_instrument'):
            try:
                broker.remember_position_instrument(
                    position_id=position.position_id,
                    symbol=position.symbol,
                )
            except Exception as exc:
                if is_broker_authorization_error(exc):
                    logger.critical(
                        'Broker authorization failed during position restore. '
                        'Stopping before continuing | position_id=%s | symbol=%s | '
                        'error=%s',
                        position.position_id,
                        position.symbol,
                        exc,
                    )
                    trade_journal.write(
                        'broker_authorization_error',
                        {
                            'stage': 'position_restore',
                            'position': position,
                            'message': str(exc),
                        },
                    )
                    raise
                logger.exception(
                    'Failed to restore broker instrument mapping | position_id=%s | '
                    'symbol=%s | error=%s',
                    position.position_id,
                    position.symbol,
                    exc,
                )
                trade_journal.write(
                    'position_restore_warning',
                    {'position': position, 'message': str(exc)},
                )

        trade_journal.write(
            'position_restored',
            {
                'position': position,
                'instrument_profile': risk_manager.instrument_profile_for(
                    position.symbol
                ),
                'risk_profile': risk_manager.risk_profile_for(position.symbol),
            },
        )
