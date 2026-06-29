from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from app.utils.commons import normalize_symbol


class CloseReason(StrEnum):
    TAKE_PROFIT = 'take_profit'
    STOP_LOSS = 'stop_loss'
    MANUAL = 'manual'
    UNKNOWN = 'unknown'


@dataclass(frozen=True)
class TradeCooldownConfig:
    enabled: bool = True
    after_take_profit_minutes: int = 30
    after_stop_loss_minutes: int = 45
    after_manual_close_minutes: int = 15
    after_unknown_close_minutes: int = 15

    def duration_minutes_for(self, close_reason: CloseReason) -> int:
        if close_reason == CloseReason.TAKE_PROFIT:
            return self.after_take_profit_minutes
        if close_reason == CloseReason.STOP_LOSS:
            return self.after_stop_loss_minutes
        if close_reason == CloseReason.MANUAL:
            return self.after_manual_close_minutes
        return self.after_unknown_close_minutes

    def duration_for(self, close_reason: CloseReason) -> timedelta:
        return timedelta(minutes=self.duration_minutes_for(close_reason))


@dataclass(frozen=True)
class TradeCooldownEntry:
    symbol: str
    side: str
    close_reason: CloseReason
    raw_close_reason: str | None
    closed_at: datetime
    expires_at: datetime
    position_id: str | None = None
    gross_pnl: float | None = None
    gross_pnl_percent: float | None = None
    created_at: datetime | None = None

    def remaining_seconds(self, now: datetime) -> int:
        return max(0, int((self.expires_at - now).total_seconds()))


MANUAL_CLOSE_REASONS = {
    'manual',
    'manual_close',
    'manually_closed',
}

STOP_LOSS_CLOSE_REASONS = {
    'stop_loss_hit',
    'trailing_stop_hit',
    'break_even_stop_hit',
}

TAKE_PROFIT_CLOSE_REASONS = {
    'take_profit_hit',
}


def close_reason_from_raw(raw_reason: str | None) -> CloseReason:
    normalized_reason = (raw_reason or '').strip().lower()

    if normalized_reason in TAKE_PROFIT_CLOSE_REASONS:
        return CloseReason.TAKE_PROFIT

    if normalized_reason in STOP_LOSS_CLOSE_REASONS:
        return CloseReason.STOP_LOSS

    if normalized_reason in MANUAL_CLOSE_REASONS:
        return CloseReason.MANUAL

    return CloseReason.UNKNOWN


def close_reason_for_closed_trade(
    raw_reason: str | None,
    gross_pnl: float | None = None,
) -> CloseReason:
    close_reason = close_reason_from_raw(raw_reason)

    if close_reason != CloseReason.UNKNOWN:
        return close_reason

    if gross_pnl is None:
        return CloseReason.UNKNOWN

    if gross_pnl > 0:
        return CloseReason.TAKE_PROFIT

    if gross_pnl < 0:
        return CloseReason.STOP_LOSS

    return CloseReason.UNKNOWN


def build_trade_cooldown_entry(
    *,
    symbol: str,
    side: str,
    config: TradeCooldownConfig,
    raw_close_reason: str | None,
    closed_at: datetime,
    position_id: str | None = None,
    gross_pnl: float | None = None,
    gross_pnl_percent: float | None = None,
    created_at: datetime | None = None,
) -> TradeCooldownEntry:
    close_reason = close_reason_for_closed_trade(
        raw_reason=raw_close_reason,
        gross_pnl=gross_pnl,
    )
    normalized_symbol = normalize_symbol(symbol)
    normalized_side = side.strip().upper()
    actual_created_at = created_at or datetime.now(timezone.utc)

    return TradeCooldownEntry(
        symbol=normalized_symbol,
        side=normalized_side,
        close_reason=close_reason,
        raw_close_reason=raw_close_reason,
        closed_at=closed_at,
        expires_at=closed_at + config.duration_for(close_reason),
        position_id=position_id,
        gross_pnl=gross_pnl,
        gross_pnl_percent=gross_pnl_percent,
        created_at=actual_created_at,
    )
