import sqlite3
from datetime import datetime
from pathlib import Path

from app.execution.position_tracker import TrackedPosition


class PositionStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def save_open_position(self, position: TrackedPosition) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO open_positions (
                    position_id,
                    symbol,
                    side,
                    amount,
                    entry_price,
                    stop_loss,
                    take_profit,
                    opened_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position.position_id,
                    position.symbol,
                    position.side,
                    position.amount,
                    position.entry_price,
                    position.stop_loss,
                    position.take_profit,
                    position.opened_at.isoformat(),
                ),
            )

    def delete_open_position(self, position_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                'DELETE FROM open_positions WHERE position_id = ?',
                (position_id,),
            )

    def load_open_positions(self) -> list[TrackedPosition]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    position_id,
                    symbol,
                    side,
                    amount,
                    entry_price,
                    stop_loss,
                    take_profit,
                    opened_at
                FROM open_positions
                ORDER BY opened_at ASC
                """
            ).fetchall()

        positions: list[TrackedPosition] = []

        for row in rows:
            (
                position_id,
                symbol,
                side,
                amount,
                entry_price,
                stop_loss,
                take_profit,
                opened_at,
            ) = row

            positions.append(
                TrackedPosition(
                    position_id=str(position_id),
                    symbol=str(symbol),
                    side=str(side),
                    amount=float(amount),
                    entry_price=float(entry_price),
                    stop_loss=float(stop_loss),
                    take_profit=float(take_profit),
                    opened_at=datetime.fromisoformat(str(opened_at)),
                )
            )

        return positions

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS open_positions (
                    position_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    amount REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    opened_at TEXT NOT NULL
                )
                """
            )