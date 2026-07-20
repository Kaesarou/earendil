from __future__ import annotations

import logging
from collections.abc import Callable

from app.brokers.base import BrokerClient
from app.execution.position_tracker import PositionTracker
from app.journal.jsonl_journal import JsonlJournal
from app.persistence.position_store import PositionStore
from app.risk.risk_manager import RiskManager
from app.runtime.broker_queries import get_fresh_position_open_states


logger = logging.getLogger(__name__)
BrokerAuthorizationErrorChecker = Callable[[Exception], bool]


def restore_persisted_positions_batched(
    *,
    position_store: PositionStore,
    position_tracker: PositionTracker,
    risk_manager: RiskManager,
    broker: BrokerClient,
    trade_journal: JsonlJournal,
    is_broker_authorization_error: BrokerAuthorizationErrorChecker,
) -> None:
    positions = position_store.load_open_positions()
    if not positions:
        logger.info('No persisted open positions to restore')
        return
    logger.warning('Restoring persisted open positions | count=%s', len(positions))
    try:
        states = get_fresh_position_open_states(
            broker,
            [position.position_id for position in positions],
        )
    except Exception as exc:  # noqa: BLE001
        if is_broker_authorization_error(exc):
            trade_journal.write(
                'broker_authorization_error',
                {
                    'stage': 'startup_position_reconciliation',
                    'position_count': len(positions),
                    'message': str(exc),
                },
            )
            raise
        states = {}
        trade_journal.write(
            'position_reconciliation_warning',
            {
                'stage': 'startup_position_reconciliation',
                'position_count': len(positions),
                'message': str(exc),
                'action': 'restore_conservatively',
            },
        )

    for position in positions:
        broker_state = states.get(position.position_id)
        position_tracker.restore_open_position(position)
        risk_manager.restore_open_position(position.symbol)
        try:
            broker.remember_position_instrument(
                position_id=position.position_id,
                symbol=position.symbol,
            )
        except Exception as exc:  # noqa: BLE001
            if is_broker_authorization_error(exc):
                trade_journal.write(
                    'broker_authorization_error',
                    {
                        'stage': 'position_restore',
                        'position': position,
                        'message': str(exc),
                    },
                )
                raise
            trade_journal.write(
                'position_restore_warning',
                {'position': position, 'message': str(exc)},
            )
        trade_journal.write(
            'position_restored',
            {
                'position': position,
                'broker_state': broker_state,
                'verification_state': (
                    'broker_open'
                    if broker_state is True
                    else 'reconciliation_required'
                ),
                'instrument_profile': risk_manager.instrument_profile_for(
                    position.symbol
                ),
                'risk_profile': risk_manager.risk_profile_for(position.symbol),
            },
        )
        if broker_state is False:
            trade_journal.write(
                'position_reconciliation_suspect',
                {
                    'source': 'startup_portfolio_snapshot',
                    'position': position,
                    'risk_reserved': True,
                    'message': 'single_startup_absence_requires_runtime_confirmation',
                },
            )
