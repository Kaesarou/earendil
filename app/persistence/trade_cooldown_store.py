import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.risk.trade_cooldown import CloseReason, TradeCooldownEntry
from app.utils.commons import normalize_symbol


class TradeCooldownStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def save_or_extend(self, entry: TradeCooldownEntry) -> TradeCooldownEntry:
        active_entry = self.find_active(
            symbol=entry.symbol,
            side=entry.side,
            now=entry.closed_at,
        )

        if active_entry is not None and active_entry.expires_at >= entry.expires_at:
            return active_entry

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO trade_cooldowns (
                    symbol,
                    side,
                    close_reason,
                    raw_close_reason,
                    closed_at,
                    expires_at,
                    position_id,
                    gross_pnl,
                    gross_pnl_percent,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalize_symbol(entry.symbol),
                    entry.side.strip().upper(),
                    entry.close_reason.value,
                    entry.raw_close_reason,
                    entry.closed_at.isoformat(),
                    entry.expires_at.isoformat(),
                    entry.position_id,
                    entry.gross_pnl,
                    entry.gross_pnl_percent,
                    entry.created_at.isoformat() if entry.created_at is not None else None,
                ),
            )

        return entry

    def find_active(
        self,
        symbol: str,
        side: str,
        now: datetime,
    ) -> TradeCooldownEntry | None:
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
                    closed_at,
                    expires_at,
                    position_id,
                    gross_pnl,
                    gross_pnl_percent,
                    created_at
                FROM trade_cooldowns
                WHERE symbol = ?
                  AND side = ?
                  AND expires_at > ?
                LIMIT 1
                """,
                (
                    normalized_symbol,
                    normalized_side,
                    now.isoformat(),
                ),
            ).fetchone()

        if row is None:
            return None

        return self._to_entry(row)

    def delete_expired(self, now: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                'DELETE FROM trade_cooldowns WHERE expires_at <= ?',
                (now.isoformat(),),
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_cooldowns (
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    close_reason TEXT NOT NULL,
                    raw_close_reason TEXT,
                    closed_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    position_id TEXT,
                    gross_pnl REAL,
                    gross_pnl_percent REAL,
                    created_at TEXT,
                    PRIMARY KEY (symbol, side)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_trade_cooldowns_expires_at
                ON trade_cooldowns(expires_at)
                """
            )

    def _to_entry(self, row: tuple[Any, ...]) -> TradeCooldownEntry:
        (
            symbol,
            side,
            close_reason,
            raw_close_reason,
            closed_at,
            expires_at,
            position_id,
            gross_pnl,
            gross_pnl_percent,
            created_at,
        ) = row

        return TradeCooldownEntry(
            symbol=str(symbol),
            side=str(side),
            close_reason=CloseReason(str(close_reason)),
            raw_close_reason=str(raw_close_reason) if raw_close_reason is not None else None,
            closed_at=datetime.fromisoformat(str(closed_at)),
            expires_at=datetime.fromisoformat(str(expires_at)),
            position_id=str(position_id) if position_id is not None else None,
            gross_pnl=self._optional_float(gross_pnl),
            gross_pnl_percent=self._optional_float(gross_pnl_percent),
            created_at=datetime.fromisoformat(str(created_at)) if created_at is not None else None,
        )

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None

        return float(value)
