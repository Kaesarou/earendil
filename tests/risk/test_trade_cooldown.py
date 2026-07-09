from datetime import datetime, timedelta, timezone

from app.risk.trade_cooldown import CloseReason, TradeCooldownConfig, build_trade_cooldown_entry, close_reason_from_raw


def test_close_reason_from_known_bot_reasons():
    assert close_reason_from_raw('take_profit_hit') == CloseReason.TAKE_PROFIT
    assert close_reason_from_raw('stop_loss_hit') == CloseReason.STOP_LOSS
    assert close_reason_from_raw('manual') == CloseReason.MANUAL


def test_build_trade_cooldown_entry_uses_configured_duration():
    closed_at = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    entry = build_trade_cooldown_entry(
        symbol=' amd ',
        side=' sell ',
        config=TradeCooldownConfig(after_take_profit_minutes=30),
        raw_close_reason='take_profit_hit',
        closed_at=closed_at,
        position_id='position-1',
        gross_pnl=1.0,
    )

    assert entry.symbol == 'AMD'
    assert entry.side == 'SELL'
    assert entry.close_reason == CloseReason.TAKE_PROFIT
    assert entry.expires_at == closed_at + timedelta(minutes=30)
