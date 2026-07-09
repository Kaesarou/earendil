from datetime import datetime, timedelta, timezone

from app.persistence.closed_trade_memory_store import ClosedTradeMemoryStore
from app.risk.trade_cooldown import CloseReason, ClosedTradeMemoryEntry


def memory_entry() -> ClosedTradeMemoryEntry:
    closed_at = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    return ClosedTradeMemoryEntry(
        symbol='AMD',
        side='SELL',
        close_reason=CloseReason.TAKE_PROFIT,
        raw_close_reason='take_profit_hit',
        opened_at=closed_at - timedelta(minutes=5),
        closed_at=closed_at,
        cooldown_expires_at=closed_at + timedelta(minutes=30),
        position_id='position-1',
        entry_price=100.0,
        exit_price=99.0,
        take_profit=99.0,
        gross_pnl=1.0,
        gross_pnl_percent=0.5,
        created_at=closed_at,
    )


def test_store_loads_active_cooldown(tmp_path):
    store = ClosedTradeMemoryStore(str(tmp_path / 'earendil.sqlite'))
    entry = memory_entry()
    store.save_or_replace(entry)

    loaded = store.find_active_cooldown(
        symbol=' amd ',
        side=' sell ',
        now=entry.closed_at + timedelta(minutes=5),
    )

    assert loaded is not None
    assert loaded.symbol == 'AMD'
    assert loaded.side == 'SELL'
    assert loaded.close_reason == CloseReason.TAKE_PROFIT


def test_store_keeps_recent_tp_after_fixed_cooldown_expiry(tmp_path):
    store = ClosedTradeMemoryStore(str(tmp_path / 'earendil.sqlite'))
    entry = memory_entry()
    store.save_or_replace(entry)
    now = entry.closed_at + timedelta(minutes=45)

    assert store.find_active_cooldown(symbol='AMD', side='SELL', now=now) is None
    assert store.find_recent_take_profit(
        symbol='AMD',
        side='SELL',
        now=now,
        lookback_minutes=60,
    ) is not None
