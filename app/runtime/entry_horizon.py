from dataclasses import dataclass

from app.instruments.models import RiskProfile
from app.market.session_rules import TradingSessionDecision
from app.runtime.trading_session_window import (
    FORCE_CLOSE_MINUTES_BEFORE_SESSION_END,
)


INSUFFICIENT_SESSION_TIME_FOR_TRADE_HORIZON = (
    'insufficient_session_time_for_trade_horizon'
)


@dataclass(frozen=True)
class EntryHorizonDecision:
    allowed: bool
    reason: str
    required_minutes: float | None
    available_minutes: float | None
    profile_key: str


def evaluate_entry_horizon(
    *,
    risk_profile: RiskProfile,
    side: str,
    session_decision: TradingSessionDecision | None,
) -> EntryHorizonDecision:
    override = risk_profile.directional_override_for(side)
    profile_key = (
        override.source if override is not None else risk_profile.profile_key
    )
    if session_decision is None:
        return EntryHorizonDecision(
            False,
            'missing_trading_session',
            None,
            None,
            profile_key,
        )
    if not session_decision.new_entries_allowed:
        return EntryHorizonDecision(
            False,
            session_decision.reason,
            None,
            session_decision.time_until_session_end_minutes,
            profile_key,
        )
    if session_decision.session_24_7:
        return EntryHorizonDecision(
            True,
            'entry_horizon_available',
            None,
            None,
            profile_key,
        )

    stale = risk_profile.stale_position_for(side)
    required_minutes = float(FORCE_CLOSE_MINUTES_BEFORE_SESSION_END)
    if stale.enabled:
        required_minutes += float(stale.max_age_minutes)
    available_minutes = session_decision.time_until_session_end_minutes
    allowed = (
        available_minutes is not None
        and available_minutes >= required_minutes
    )
    return EntryHorizonDecision(
        allowed,
        (
            'entry_horizon_available'
            if allowed
            else INSUFFICIENT_SESSION_TIME_FOR_TRADE_HORIZON
        ),
        required_minutes,
        available_minutes,
        profile_key,
    )
