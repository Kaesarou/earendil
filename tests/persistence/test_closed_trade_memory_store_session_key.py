import sqlite3
from datetime import datetime, timedelta, timezone

from app.persistence.closed_trade_memory_store import ClosedTradeMemoryStore
from app.risk.trade_cooldown import CloseReason, ClosedTradeMemoryEntry

NOW = datetime(2026, 7, 10, 15, 0, tzinfo=timezone.utc)


def entry():
    return ClosedTradeMemoryEntry(
        symbol='MU',
        side='SELL',
        close_reason=CloseReason.STOP_LOSS,
        raw_close_reason='stop_loss_hit',
        opened_at=NOW - timedelta(minutes=5),
        closed_at=NOW,
        cooldown_expires_at=NOW + timedelta(minutes=45),
        position_id='position-1',
        created_at=NOW,
        session_key='US-2026-07-10',
    )


def test_session_key_is_persisted_across_restart(tmp_path):
    path = str(tmp_path / 'earendil.sqlite')
    ClosedTradeMemoryStore(path).save_or_replace(entry())

    restored = ClosedTradeMemoryStore(path).find_latest(
        symbol='MU',
        side='SELL',
    )

    assert restored is not None
    assert restored.session_key == 'US-2026-07-10'


def test_existing_schema_is_migrated_with_session_key_column(tmp_path):
    path = str(tmp_path / 'earendil.sqlite')
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE closed_trade_memory (
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                close_reason TEXT NOT NULL,
                raw_close_reason TEXT,
                opened_at TEXT,
                closed_at TEXT NOT NULL,
                cooldown_expires_at TEXT NOT NULL,
                position_id TEXT,
                entry_price REAL,
                exit_price REAL,
                stop_loss REAL,
                take_profit REAL,
                highest_price REAL,
                lowest_price REAL,
                gross_pnl REAL,
                gross_pnl_percent REAL,
                created_at TEXT,
                PRIMARY KEY (symbol, side)
            )
            """
        )

    store = ClosedTradeMemoryStore(path)
    store.save_or_replace(entry())

    with sqlite3.connect(path) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                'PRAGMA table_info(closed_trade_memory)'
            ).fetchall()
        }

    assert 'session_key' in columns
    assert store.find_latest(symbol='MU', side='SELL').session_key == 'US-2026-07-10'
