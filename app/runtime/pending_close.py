from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from app.execution.position_tracker import PositionCloseSignal


class CloseState(StrEnum):
    SUBMITTING = 'close_submitting'
    PENDING_CONFIRMATION = 'close_pending_confirmation'
    SUBMISSION_UNKNOWN = 'close_submission_unknown'


@dataclass(frozen=True)
class PendingClose:
    position_id: str
    symbol: str
    signal: PositionCloseSignal
    source: str
    state: CloseState
    requested_at: datetime
    submitted_at: datetime | None = None
    accepted_at: datetime | None = None
    close_order_id: str | None = None
    reference_id: str | None = None
    confirmation_checks: int = 0
    last_confirmation_at: datetime | None = None
    last_error: str | None = None
    session_decision: Any = None

    def mark_submitted(
        self,
        *,
        submitted_at: datetime,
        accepted_at: datetime,
        close_order_id: str | None,
        reference_id: str | None,
    ) -> 'PendingClose':
        return replace(
            self,
            state=CloseState.PENDING_CONFIRMATION,
            submitted_at=_as_utc(submitted_at),
            accepted_at=_as_utc(accepted_at),
            close_order_id=close_order_id,
            reference_id=reference_id,
            last_error=None,
        )

    def mark_submission_unknown(self, *, error: Exception) -> 'PendingClose':
        return replace(
            self,
            state=CloseState.SUBMISSION_UNKNOWN,
            last_error=str(error),
        )

    def observe_still_open(self, *, observed_at: datetime) -> 'PendingClose':
        return replace(
            self,
            confirmation_checks=self.confirmation_checks + 1,
            last_confirmation_at=_as_utc(observed_at),
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
