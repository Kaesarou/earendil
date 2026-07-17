from datetime import datetime, timezone

from app.instruments.base_configs import (
    CRYPTO_CONFIG,
    EQUITY_EU_CONFIG,
    EQUITY_US_CONFIG,
)
from app.instruments.models import AssetClass
from app.runtime.entry_horizon import (
    INSUFFICIENT_SESSION_TIME_FOR_TRADE_HORIZON,
    evaluate_entry_horizon,
)
from app.runtime.trading_session_window import TradingSessionDecision


NOW = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


def decision(asset_class, *, minutes, session_24_7=False, allowed=True):
    return TradingSessionDecision(
        asset_class=asset_class,
        session_active=True,
        session_24_7=session_24_7,
        collect_snapshots=True,
        new_entries_allowed=allowed,
        force_close_required=False,
        reason='session_tradable' if allowed else 'too_close_to_session_end',
        session_start_time=NOW,
        session_end_time=NOW,
        time_until_session_end_minutes=minutes,
        session_key=f'{asset_class.value}:session',
    )


def test_us_fixed_profile_requires_stale_horizon_plus_force_close_buffer():
    rejected = evaluate_entry_horizon(
        risk_profile=EQUITY_US_CONFIG.risk,
        side='BUY',
        session_decision=decision(AssetClass.EQUITY_US, minutes=79.9),
    )
    allowed = evaluate_entry_horizon(
        risk_profile=EQUITY_US_CONFIG.risk,
        side='BUY',
        session_decision=decision(AssetClass.EQUITY_US, minutes=80.0),
    )
    assert rejected.reason == INSUFFICIENT_SESSION_TIME_FOR_TRADE_HORIZON
    assert rejected.required_minutes == 80.0
    assert allowed.allowed
    assert allowed.profile_key == 'us_intraday_fixed_v1'


def test_eu_buy_and_sell_use_their_own_horizons():
    buy = evaluate_entry_horizon(
        risk_profile=EQUITY_EU_CONFIG.risk,
        side='BUY',
        session_decision=decision(AssetClass.EQUITY_EU, minutes=199.9),
    )
    sell = evaluate_entry_horizon(
        risk_profile=EQUITY_EU_CONFIG.risk,
        side='SELL',
        session_decision=decision(AssetClass.EQUITY_EU, minutes=95.0),
    )
    assert not buy.allowed
    assert buy.required_minutes == 200.0
    assert buy.profile_key == 'eu_trend_buy_v1'
    assert sell.allowed
    assert sell.required_minutes == 95.0
    assert sell.profile_key == 'eu_intraday_fixed_v1'


def test_24_7_profile_is_not_blocked_by_finite_session_horizon():
    result = evaluate_entry_horizon(
        risk_profile=CRYPTO_CONFIG.risk,
        side='BUY',
        session_decision=decision(
            AssetClass.CRYPTO,
            minutes=None,
            session_24_7=True,
        ),
    )
    assert result.allowed
    assert result.required_minutes is None
