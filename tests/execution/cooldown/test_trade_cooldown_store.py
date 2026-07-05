from datetime import datetime, timedelta, timezone

from app.persistence.trade_cooldown_store import TradeCooldownStore
from app.risk.trade_cooldown import CloseReason, TradeCooldownEntry


def cooldown_entry(
    *,
    symbol: str = 'AMD',
    side: str = 'SELL',
    close_reason: CloseReason = CloseReason.TAKE_PROFIT,
    closed_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> TradeCooldownEntry:
    actual_closed_at = closed_at or datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)

    return TradeCooldownEntry(
        symbol=symbol,
        side=side,
        close_reason=close_reason,
        raw_close_reason='take_profit_hit',
        closed_at=actual_closed_at,
        expires_at=expires_at or actual_closed_at + timedelta(minutes=30),
        position_id='position-1',
        gross_pnl=1.0,
        gross_pnl_percent=0.5,
        created_at=actual_closed_at,
    )


def test_trade_cooldown_store_saves_and_loads_active_cooldown(tmp_path):
    store = TradeCooldownStore(str(tmp_path / 'earendil.sqlite'))
    entry = cooldown_entry()

    store.save_or_extend(entry)

    loaded_entry = store.find_active(
        symbol=' amd ',
        side=' sell ',
        now=entry.closed_at + timedelta(minutes=5),
    )

    assert loaded_entry is not None
    assert loaded_entry.symbol == 'AMD'
    assert loaded_entry.side == 'SELL'
    assert loaded_entry.close_reason == CloseReason.TAKE_PROFIT
    assert loaded_entry.expires_at == entry.expires_at


def test_trade_cooldown_store_does_not_shorten_existing_cooldown(tmp_path):
    store = TradeCooldownStore(str(tmp_path / 'earendil.sqlite'))
    closed_at = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    long_entry = cooldown_entry(
        closed_at=closed_at,
        expires_at=closed_at + timedelta(minutes=45),
    )
    short_entry = cooldown_entry(
        closed_at=closed_at + timedelta(minutes=5),
        expires_at=closed_at + timedelta(minutes=20),
    )

    store.save_or_extend(long_entry)
    saved_entry = store.save_or_extend(short_entry)

    assert saved_entry.expires_at == long_entry.expires_at

    loaded_entry = store.find_active(
        symbol='AMD',
        side='SELL',
        now=closed_at + timedelta(minutes=10),
    )

    assert loaded_entry is not None
    assert loaded_entry.expires_at == long_entry.expires_at


def test_trade_cooldown_store_extends_existing_cooldown(tmp_path):
    store = TradeCooldownStore(str(tmp_path / 'earendil.sqlite'))
    closed_at = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    short_entry = cooldown_entry(
        closed_at=closed_at,
        expires_at=closed_at + timedelta(minutes=20),
    )
    long_entry = cooldown_entry(
        closed_at=closed_at + timedelta(minutes=5),
        expires_at=closed_at + timedelta(minutes=45),
    )

    store.save_or_extend(short_entry)
    saved_entry = store.save_or_extend(long_entry)

    assert saved_entry.expires_at == long_entry.expires_at


def test_trade_cooldown_store_ignores_expired_cooldown(tmp_path):
    store = TradeCooldownStore(str(tmp_path / 'earendil.sqlite'))
    closed_at = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    entry = cooldown_entry(
        closed_at=closed_at,
        expires_at=closed_at + timedelta(minutes=1),
    )

    store.save_or_extend(entry)

    assert store.find_active(
        symbol='AMD',
        side='SELL',
        now=closed_at + timedelta(minutes=2),
    ) is None
