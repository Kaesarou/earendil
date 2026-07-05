import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

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
                    position_id, symbol, side, amount, entry_price, stop_loss,
                    take_profit, opened_at, initial_stop_loss, highest_price,
                    lowest_price, breakeven_stop_enabled, breakeven_trigger_percent,
                    breakeven_buffer_percent, trailing_stop_enabled,
                    trailing_stop_trigger_percent, trailing_stop_distance_percent,
                    estimated_total_cost_percent, stale_position_enabled,
                    stale_position_max_age_minutes,
                    stale_position_min_favorable_move_percent,
                    stale_position_buffer_percent
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    position.initial_stop_loss,
                    position.highest_price,
                    position.lowest_price,
                    int(position.breakeven_stop_enabled),
                    position.breakeven_trigger_percent,
                    position.breakeven_buffer_percent,
                    int(position.trailing_stop_enabled),
                    position.trailing_stop_trigger_percent,
                    position.trailing_stop_distance_percent,
                    position.estimated_total_cost_percent,
                    int(position.stale_position_enabled),
                    position.stale_position_max_age_minutes,
                    position.stale_position_min_favorable_move_percent,
                    position.stale_position_buffer_percent,
                ),
            )

    def delete_open_position(self, position_id: str) -> None:
        with self._connect() as connection:
            connection.execute('DELETE FROM open_positions WHERE position_id = ?', (position_id,))

    def load_open_positions(self) -> list[TrackedPosition]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    position_id, symbol, side, amount, entry_price, stop_loss,
                    take_profit, opened_at, initial_stop_loss, highest_price,
                    lowest_price, breakeven_stop_enabled, breakeven_trigger_percent,
                    breakeven_buffer_percent, trailing_stop_enabled,
                    trailing_stop_trigger_percent, trailing_stop_distance_percent,
                    estimated_total_cost_percent, stale_position_enabled,
                    stale_position_max_age_minutes,
                    stale_position_min_favorable_move_percent,
                    stale_position_buffer_percent
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
                initial_stop_loss,
                highest_price,
                lowest_price,
                breakeven_stop_enabled,
                breakeven_trigger_percent,
                breakeven_buffer_percent,
                trailing_stop_enabled,
                trailing_stop_trigger_percent,
                trailing_stop_distance_percent,
                estimated_total_cost_percent,
                stale_position_enabled,
                stale_position_max_age_minutes,
                stale_position_min_favorable_move_percent,
                stale_position_buffer_percent,
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
                    initial_stop_loss=self._optional_float(initial_stop_loss),
                    highest_price=self._optional_float(highest_price),
                    lowest_price=self._optional_float(lowest_price),
                    breakeven_stop_enabled=bool(breakeven_stop_enabled),
                    breakeven_trigger_percent=float(breakeven_trigger_percent),
                    breakeven_buffer_percent=float(breakeven_buffer_percent),
                    trailing_stop_enabled=bool(trailing_stop_enabled),
                    trailing_stop_trigger_percent=float(trailing_stop_trigger_percent),
                    trailing_stop_distance_percent=float(trailing_stop_distance_percent),
                    estimated_total_cost_percent=float(estimated_total_cost_percent),
                    stale_position_enabled=bool(stale_position_enabled),
                    stale_position_max_age_minutes=int(stale_position_max_age_minutes),
                    stale_position_min_favorable_move_percent=float(
                        stale_position_min_favorable_move_percent
                    ),
                    stale_position_buffer_percent=float(stale_position_buffer_percent),
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
                    opened_at TEXT NOT NULL,
                    initial_stop_loss REAL,
                    highest_price REAL,
                    lowest_price REAL,
                    breakeven_stop_enabled INTEGER NOT NULL DEFAULT 0,
                    breakeven_trigger_percent REAL NOT NULL DEFAULT 0,
                    breakeven_buffer_percent REAL NOT NULL DEFAULT 0,
                    trailing_stop_enabled INTEGER NOT NULL DEFAULT 0,
                    trailing_stop_trigger_percent REAL NOT NULL DEFAULT 0,
                    trailing_stop_distance_percent REAL NOT NULL DEFAULT 0,
                    estimated_total_cost_percent REAL NOT NULL DEFAULT 0,
                    stale_position_enabled INTEGER NOT NULL DEFAULT 0,
                    stale_position_max_age_minutes INTEGER NOT NULL DEFAULT 0,
                    stale_position_min_favorable_move_percent REAL NOT NULL DEFAULT 0,
                    stale_position_buffer_percent REAL NOT NULL DEFAULT 0
                )
                """
            )

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        return float(value)
