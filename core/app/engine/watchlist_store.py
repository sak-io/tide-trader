import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.models.domain import WatchlistItem

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY,
    added_at TEXT NOT NULL
)
"""


class WatchlistStore:
    """SQLite-backed persistence for the user's manually curated watchlist.

    One bucket of the scan universe (the other being Alpaca's most-active/movers
    lists) - see `app.engine.screener.build_scan_universe`. Follows the same
    single-file, schema-on-init pattern as `state_store.py`.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        parent = Path(self.db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def list(self) -> list[WatchlistItem]:
        with self._connect() as conn:
            rows = conn.execute("SELECT symbol, added_at FROM watchlist ORDER BY added_at").fetchall()
        return [WatchlistItem(symbol=row[0], added_at=row[1]) for row in rows]

    def add(self, symbol: str) -> WatchlistItem:
        symbol = symbol.strip().upper()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO watchlist (symbol, added_at) VALUES (?, ?) ON CONFLICT(symbol) DO NOTHING",
                (symbol, datetime.now(UTC).isoformat()),
            )
            conn.commit()
            row = conn.execute(
                "SELECT symbol, added_at FROM watchlist WHERE symbol = ?", (symbol,)
            ).fetchone()
        return WatchlistItem(symbol=row[0], added_at=row[1])

    def remove(self, symbol: str) -> bool:
        symbol = symbol.strip().upper()
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
            conn.commit()
            return cursor.rowcount > 0
