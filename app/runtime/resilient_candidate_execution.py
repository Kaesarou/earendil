from __future__ import annotations

import logging
from datetime import datetime

from app.runtime.async_candidate_execution import (
    AsyncCandidateExecutionCoordinator,
    _OrderContext,
    _UnknownOrder,
)
from app.runtime.broker_queries import (
    order_id_from_confirmation_error,
    reference_id_from_confirmation_error,
    submitted_at_from_confirmation_error,
)
from app.runtime.pending_candidate_lifecycle import keep_pending_waiting


logger = logging.getLogger(__name__)


class ResilientCandidateExecutionCoordinator(
    AsyncCandidateExecutionCoordinator
):
    def _mark_confirmation_unknown(
        self,
        context: _OrderContext,
        exc: Exception,
        *,
        now: datetime,
    ) -> None:
        reservation = self._reservations.get(context.reservation_id)
        if reservation is not None:
            reservation.state = 'confirmation_unknown'
        order_id = order_id_from_confirmation_error(exc)
        reference_id = reference_id_from_confirmation_error(exc)
        submitted_at = submitted_at_from_confirmation_error(
            exc,
            context.submitted_at,
        )
        unknown_context = _OrderContext(
            reservation_id=context.reservation_id,
            candidate=context.candidate,
            trade_plan=context.trade_plan,
            economics=context.economics,
            effective_sl_tp=context.effective_sl_tp,
            instrument_profile=context.instrument_profile,
            risk_profile=context.risk_profile,
            submitted_at=submitted_at,
        )
        self._unknown_orders[context.reservation_id] = _UnknownOrder(
            context=unknown_context,
            order_id=order_id,
            reference_id=reference_id,
            attempts=0,
            first_unknown_at=now,
            next_lookup_at=now,
        )
        keep_pending_waiting(
            candidate=context.candidate,
            reason='order_confirmation_unknown',
            pending_entry_manager=self.pending_entry_manager,
            trade_journal=self.trade_journal,
        )
        self.trade_journal.write(
            'order_confirmation_unknown',
            {
                'reservation_id': context.reservation_id,
                'order_id': order_id,
                'reference_id': reference_id,
                'symbol': context.candidate.symbol,
                'candidate': context.candidate,
                'trade_plan': context.trade_plan,
                'submitted_at': submitted_at,
                'message': str(exc),
                'risk_reserved': True,
            },
        )

    def _record_order_failure(
        self,
        context: _OrderContext,
        exc: Exception,
    ) -> None:
        keep_pending_waiting(
            candidate=context.candidate,
            reason='candidate_execution_error',
            pending_entry_manager=self.pending_entry_manager,
            trade_journal=self.trade_journal,
        )
        logger.error(
            'Candidate execution error | symbol=%s | action=%s | error=%s',
            context.candidate.symbol,
            context.candidate.signal.action,
            exc,
        )
        payload = {
            'reservation_id': context.reservation_id,
            'symbol': context.candidate.symbol,
            'candidate': context.candidate,
            'message': str(exc),
        }
        self.trade_journal.write('order_failed', payload)
        self.trade_journal.write('candidate_execution_error', payload)
