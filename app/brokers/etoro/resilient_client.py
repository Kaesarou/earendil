from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from app.brokers.base import (
    ClosePositionRejectedError,
    ClosePositionSubmission,
    ClosePositionSubmissionUnknownError,
    OpenPositionResult,
)
from app.brokers.etoro.close_order_payload_builder import build_close_order_payload
from app.brokers.etoro.etoro_client import EtoroClient
from app.brokers.etoro.order_confirmation_error import (
    EtoroOrderConfirmationUnknownError,
)
from app.brokers.etoro.position_instrument_cache import (
    remember_position_instrument_id,
    require_position_instrument_id,
)


logger = logging.getLogger(__name__)


class ResilientEtoroClient(EtoroClient):
    """Preserve exposure while accepted open orders remain uncertain."""

    def open_position(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_loss: float,
        take_profit: float,
    ) -> OpenPositionResult:
        normalized_side = self._normalize_side(side)
        self._ensure_side_is_allowed(normalized_side)
        instrument_id = self._find_instrument_id(symbol)
        payload = self._build_open_order_payload(
            instrument_id=instrument_id,
            side=normalized_side,
            amount=amount,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        logger.warning(
            'Sending eToro order | env=%s | symbol=%s | side=%s | '
            'transaction=%s | instrument_id=%s | amount=%s | '
            'bot_stop_loss=%s | take_profit=%s | StopLossRate=%s | '
            'TakeProfitRate=%s | leverage=%s | payload=%s',
            self.env,
            symbol,
            normalized_side,
            payload.get('transaction'),
            instrument_id,
            amount,
            stop_loss,
            take_profit,
            payload.get('StopLossRate'),
            payload.get('TakeProfitRate'),
            payload.get('leverage'),
            payload,
        )
        submitted_at = datetime.now(timezone.utc)
        order_response = self._post(self._open_order_path(), payload)
        logger.info('eToro order response: %s', order_response)
        order_id = self._extract_order_id(order_response)
        reference_id = self._extract_reference_id(order_response)
        logger.info(
            'eToro order submitted | order_id=%s | reference_id=%s',
            order_id,
            reference_id,
        )
        try:
            order_details = self._wait_for_executed_order(
                order_id,
                require_position_details=True,
            )
        except Exception as exc:  # accepted order may exist
            if 'eToro order rejected:' in str(exc):
                raise
            raise EtoroOrderConfirmationUnknownError(
                order_id=order_id,
                reference_id=reference_id,
                symbol=symbol.strip().upper(),
                side=normalized_side,
                amount=amount,
                submitted_at=submitted_at,
                cause=exc,
            ) from exc

        executed_positions = self._extract_executed_position_details_list(
            order_details
        )
        if len(executed_positions) != 1:
            raise EtoroOrderConfirmationUnknownError(
                order_id=order_id,
                reference_id=reference_id,
                symbol=symbol.strip().upper(),
                side=normalized_side,
                amount=amount,
                submitted_at=submitted_at,
                cause=RuntimeError(
                    'unsupported executed position count: '
                    f'{len(executed_positions)}'
                ),
            )
        executed_position = executed_positions[0]
        remember_position_instrument_id(
            position_instruments=self.position_instruments,
            position_id=executed_position.position_id,
            instrument_id=instrument_id,
        )
        logger.info(
            'eToro position confirmed | order_id=%s | position_id=%s | '
            'instrument_id=%s | side=%s | executed_entry_price=%s',
            order_id,
            executed_position.position_id,
            instrument_id,
            normalized_side,
            executed_position.executed_entry_price,
        )
        return OpenPositionResult(
            position_id=executed_position.position_id,
            executed_entry_price=executed_position.executed_entry_price,
        )

    def close_position(self, position_id: str) -> ClosePositionSubmission:
        try:
            instrument_id = require_position_instrument_id(
                position_instruments=self.position_instruments,
                position_id=position_id,
            )
        except Exception as exc:
            raise ClosePositionRejectedError(
                position_id=position_id,
                message=(
                    'Close submission was not sent because broker position '
                    f'metadata is unavailable: position_id={position_id}'
                ),
                cause=exc,
            ) from exc

        submitted_at = datetime.now(timezone.utc)
        try:
            response = self._post(
                self._close_position_path(position_id),
                build_close_order_payload(instrument_id),
            )
        except requests.HTTPError as exc:
            status = getattr(exc.response, 'status_code', None)
            if (
                status is not None
                and 400 <= status < 500
                and status not in {408, 409, 425, 429}
            ):
                raise ClosePositionRejectedError(
                    position_id=position_id,
                    message=(
                        'eToro explicitly rejected close submission: '
                        f'position_id={position_id}, status={status}'
                    ),
                    cause=exc,
                ) from exc
            raise ClosePositionSubmissionUnknownError(
                position_id=position_id,
                submitted_at=submitted_at,
                cause=exc,
            ) from exc
        except requests.RequestException as exc:
            raise ClosePositionSubmissionUnknownError(
                position_id=position_id,
                submitted_at=submitted_at,
                cause=exc,
            ) from exc

        try:
            close_order_id = self._extract_order_id(response)
        except (KeyError, TypeError, ValueError):
            close_order_id = None
        try:
            reference_id = self._extract_reference_id(response)
        except (KeyError, TypeError, ValueError):
            reference_id = None

        if not self._is_close_response_accepted(response, position_id):
            if self._is_order_rejected(response):
                raise ClosePositionRejectedError(
                    position_id=position_id,
                    message=(
                        'eToro explicitly rejected close submission: '
                        f'position_id={position_id}, response={response}'
                    ),
                    broker_response=response,
                )
            raise ClosePositionSubmissionUnknownError(
                position_id=position_id,
                submitted_at=submitted_at,
                cause=RuntimeError(
                    'eToro close response did not prove acceptance'
                ),
                broker_response=response,
                close_order_id=close_order_id,
                reference_id=reference_id,
            )

        accepted_at = datetime.now(timezone.utc)
        logger.info(
            'eToro close submitted | position_id=%s | close_order_id=%s | '
            'reference_id=%s',
            position_id,
            close_order_id,
            reference_id,
        )
        return ClosePositionSubmission(
            position_id=position_id,
            close_order_id=close_order_id,
            reference_id=reference_id,
            submitted_at=submitted_at,
            accepted_at=accepted_at,
            broker_response=response,
        )
