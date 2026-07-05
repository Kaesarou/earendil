from datetime import datetime, timedelta, timezone

from app.risk.trade_cooldown import (
    CloseReason,
    TradeCooldownConfig,
    build_trade_cooldown_entry,
    close_reason_for_closed_trade,
    close_reason_from_raw,
)


def test_close_reason_from_known_bot_reasons():
    assert close_reason_from_raw('take_profit_hit') == CloseReason.TAKE_PROFIT
    assert close_reason_from_raw('stop_loss_hit') == CloseReason.STOP_LOSS
    assert close_reason_from_raw('trailing_stop_hit') == CloseReason.UNKNOWN
    assert close_reason_from_raw('break_even_stop_hit') == CloseReason.UNKNOWN
    assert close_reason_from_raw('manual') == CloseReason.MANUAL


def test_close_reason_falls_back_to_pnl_when_reason_is_unknown():
    assert close_reason_for_closed_trade('unknown', gross_pnl=1.25) == CloseReason.TAKE_PROFIT
    assert close_reason_for_closed_trade('unknown', gross_pnl=-0.75) == CloseReason.STOP_LOSS
    assert close_reason_for_closed_trade('unknown', gross_pnl=0.0) == CloseReason.UNKNOWN
    assert close_reason_for_closed_trade('unknown', gross_pnl=None) == CloseReason.UNKNOWN


def test_protected_exit_reason_uses_pnl_for_cooldown_classification():
    assert close_reason_for_closed_trade('trailing_stop_hit', gross_pnl=1.25) == CloseReason.TAKE_PROFIT
    assert close_reason_for_closed_trade('break_even_stop_hit', gross_pnl=0.25) == CloseReason.TAKE_PROFIT
    assert close_reason_for_closed_trade('trailing_stop_hit', gross_pnl=-0.75) == CloseReason.STOP_LOSS
    assert close_reason_for_closed_trade('break_even_stop_hit', gross_pnl=0.0) == CloseReason.UNKNOWN


def test_build_trade_cooldown_entry_uses_configured_duration():
    closed_at = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config = TradeCooldownConfig(after_take_profit_minutes=30)

    entry = build_trade_cooldown_entry(
        symbol=' amd ',
        side=' sell ',
        config=config,
        raw_close_reason='take_profit_hit',
        closed_at=closed_at,
        position_id='position-1',
        gross_pnl=1.0,
        gross_pnl_percent=0.5,
    )

    assert entry.symbol == 'AMD'
    assert entry.side == 'SELL'
    assert entry.close_reason == CloseReason.TAKE_PROFIT
    assert entry.expires_at == closed_at + timedelta(minutes=30)
    assert entry.position_id == 'position-1'


def test_build_trade_cooldown_entry_uses_take_profit_duration_for_positive_protected_exit():
    closed_at = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config = TradeCooldownConfig(after_take_profit_minutes=30, after_stop_loss_minutes=45)

    entry = build_trade_cooldown_entry(
        symbol='AMD',
        side='SELL',
        config=config,
        raw_close_reason='trailing_stop_hit',
        closed_at=closed_at,
        gross_pnl=1.0,
    )

    assert entry.close_reason == CloseReason.TAKE_PROFIT
    assert entry.expires_at == closed_at + timedelta(minutes=30)
