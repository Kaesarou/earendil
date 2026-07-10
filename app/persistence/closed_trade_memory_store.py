import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.risk.trade_cooldown import CloseReason, ClosedTradeMemoryEntry
from app.utils.commons import normalize_symbol


class ClosedTradeMemoryStore:
    def __init__(self, path: str, retention_minutes: int = 240):
        self.path = Path(path)
        self.retention_minutes = retention_minutes
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def save_or_replace(self, entry: ClosedTradeMemoryEntry) -> ClosedTradeMemoryEntry:
        existing_entry = self.find_latest(symbol=entry.symbol, side=entry.side)
        if existing_entry is not None and existing_entry.closed_at > entry.closed_at:
            return existing_entry

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO closed_trade_memory (
                    symbol,
                    side,
                    close_reason,
                    raw_close_reason,
                    opened_at,
                    closed_at,
                    cooldown_expires_at,
                    position_id,
                    entry_price,
                    exit_price,
                    stop_loss,
                    take_profit,
                    highest_price,
                    lowest_price,
                    gross_pnl,
                    gross_pnl_percent,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalize_symbol(entry.symbol),
                    entry.side.strip().upper(),
                    entry.close_reason.value,
                    entry.raw_close_reason,
                    entry.opened_at.isoformat() if entry.opened_at is not None else None,
                    entry.closed_at.isoformat(),
                    entry.cooldown_expires_at.isoformat(),
                    entry.position_id,
                    entry.entry_price,
                    entry.exit_price,
                    entry.stop_loss,
                    entry.take_profit,
                    entry.highest_price,
                    entry.lowest_price,
                    entry.gross_pnl,
                    entry.gross_pnl_percent,
                    entry.created_at.isoformat() if entry.created_at is not None else None,
                ),
            )

        return entry

    def find_latest(self, symbol: str, side: str) -> ClosedTradeMemoryEntry | None:
        normalized_symbol = normalize_symbol(symbol)
        normalized_side = side.strip().upper()

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    symbol,
                    side,
                    close_reason,
                    raw_close_reason,
                    opened_at,
                    closed_at,
                    cooldown_expires_at,
                    position_id,
                    entry_price,
                    exit_price,
                    stop_loss,
                    take_profit,
                    highest_price,
                    lowest_price,
                    gross_pnl,
                    gross_pnl_percent,
                    created_at
                FROM closed_trade_memory
                WHERE symbol = ?
                  AND side = ?
                LIMIT 1
                """,
                (
                    normalized_symbol,
                    normalized_side,
                ),
            ).fetchone()

        if row is None:
            return None

        return self._to_entry(row)

    def find_latest_stop_loss(self, *, symbol: str) -> ClosedTradeMemoryEntry | None:
        normalized_symbol = normalize_symbol(symbol)

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    symbol,
                    side,
                    close_reason,
                    raw_close_reason,
                    opened_at,
                    closed_at,
                    cooldown_expires_at,
                    position_id,
                    entry_price,
                    exit_price,
                    stop_loss,
                    take_profit,
                    highest_price,
                    lowest_price,
                    gross_pnl,
                    gross_pnl_percent,
                    created_at
                FROM closed_trade_memory
                WHERE symbol = ?
                  AND close_reason = ?
                ORDER BY closed_at DESC
                LIMIT 1
                """,
                (
                    normalized_symbol,
                    CloseReason.STOP_LOSS.value,
                ),
            ).fetchone()

        if row is None:
            return None

        return self._to_entry(row)

    def find_active_cooldown(
        self,
        *,
        symbol: str,
        side: str,
        now: datetime,
    ) -> ClosedTradeMemoryEntry | None:
        entry = self.find_latest(symbol=symbol, side=side)
        if entry is None or entry.cooldown_expires_at <= now:
            return None
        return entry

    def find_recent_take_profit(
        self,
        *,
        symbol: str,
        side: str,
        now: datetime,
        lookback_minutes: int,
    ) -> ClosedTradeMemoryEntry | None:
        entry = self.find_latest(symbol=symbol, side=side)
        if entry is None or entry.close_reason != CloseReason.TAKE_PROFIT:
            return None
        if lookback_minutes <= 0:
            return None
        if entry.closed_at < now - timedelta(minutes=lookback_minutes):
            return None
        return entry

    def delete_expired(self, now: datetime) -> None:
        retention_cutoff = now - timedelta(minutes=self.retention_minutes)
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM closed_trade_memory
                WHERE cooldown_expires_at <= ?
                  AND closed_at <= ?
                """,
                (now.isoformat(), retention_cutoff.isoformat()),
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS closed_trade_memory (
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
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_closed_trade_memory_cooldown_expires_at
                ON closed_trade_memory(cooldown_expires_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_closed_trade_memory_closed_at
                ON closed_trade_memory(closed_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_closed_trade_memory_symbol_close_reason
                ON closed_trade_memory(symbol, close_reason, closed_at)
                """
            )
            self._migrate_legacy_trade_cooldowns(connection)

    def _migrate_legacy_trade_cooldowns(self, connection: sqlite3.Connection) -> None:
        legacy_table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'trade_cooldowns'
            """
        ).fetchone()
        if legacy_table is None:
            return

        connection.execute(
            """
            INSERT OR IGNORE INTO closed_trade_memory (
                symbol,
                side,
                close_reason,
                raw_close_reason,
                opened_at,
                closed_at,
                cooldown_expires_at,
                position_id,
                entry_price,
                exit_price,
                stop_loss,
                take_profit,
                highest_price,
                lowest_price,
                gross_pnl,
                gross_pnl_percent,
                created_at
            )
            SELECT
                symbol,
                side,
                close_reason,
                raw_close_reason,
                NULL,
                closed_at,
                expires_at,
                position_id,
                NULL,
                NULL,
                NULL,
                NULL,
                NULL,
                NULL,
                gross_pnl,
                gross_pnl_percent,
                created_at
            FROM trade_cooldowns
            """
        )
        connection.execute('DROP TABLE trade_cooldowns')

    def _to_entry(self, row: tuple[Any, ...]) -> ClosedTradeMemoryEntry:
        (
            symbol,
            side,
            close_reason,
            raw_close_reason,
            opened_at,
            closed_at,
            cooldown_expires_at,
            position_id,
            entry_price,
            exit_price,
            stop_loss,
            take_profit,
            highest_price,
            lowest_price,
            gross_pnl,
            gross_pnl_percent,
            created_at,
        ) = row

        return ClosedTradeMemoryEntry(
            symbol=str(symbol),
            side=str(side),
            close_reason=CloseReason(str(close_reason)),
            raw_close_reason=str(raw_close_reason) if raw_close_reason is not None else None,
            opened_at=(
                datetime.fromisoformat(str(opened_at)) if opened_at is not None else None
            ),
            closed_at=datetime.fromisoformat(str(closed_at)),
            cooldown_expires_at=datetime.fromisoformat(str(cooldown_expires_at)),
            position_id=str(position_id) if position_id is not None else None,
            entry_price=self._optional_float(entry_price),
            exit_price=self._optional_float(exit_price),
            stop_loss=self._optional_float(stop_loss),
            take_profit=self._optional_float(take_profit),
            highest_price=self._optional_float(highest_price),
            lowest_price=self._optional_float(lowest_price),
            gross_pnl=self._optional_float(gross_pnl),
            gross_pnl_percent=self._optional_float(gross_pnl_percent),
            created_at=(
                datetime.fromisoformat(str(created_at)) if created_at is not None else None
            ),
        )

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None

        return float(value)
