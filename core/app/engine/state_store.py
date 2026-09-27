import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS risk_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    kill_switch_active INTEGER NOT NULL DEFAULT 0,
    kill_switch_reason TEXT,
    day TEXT,
    day_start_equity REAL,
    last_equity REAL,
    updated_at TEXT
)
"""


@dataclass
class RiskState:
    kill_switch_active: bool = False
    kill_switch_reason: str | None = None
    day: str | None = None
    day_start_equity: float | None = None
    last_equity: float | None = None


class StateStore:
    """SQLite-backed persistence for risk manager state.

    Backed by a single-row table on disk so the kill switch and daily-drawdown
    tracking survive a process restart, rather than silently resetting.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        parent = Path(self.db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
            conn.execute(_SCHEMA)
            conn.execute("INSERT OR IGNORE INTO risk_state (id, kill_switch_active) VALUES (1, 0)")
            conn.commit()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def load(self) -> RiskState:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT kill_switch_active, kill_switch_reason, day, day_start_equity, last_equity "
                "FROM risk_state WHERE id = 1"
            ).fetchone()

        # __init__ always inserts this row, so it's guaranteed to exist here.
        return RiskState(
            kill_switch_active=bool(row[0]),
            kill_switch_reason=row[1],
            day=row[2],
            day_start_equity=row[3],
            last_equity=row[4],
        )

    def save(self, state: RiskState) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE risk_state
                SET kill_switch_active = ?, kill_switch_reason = ?, day = ?,
                    day_start_equity = ?, last_equity = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    int(state.kill_switch_active),
                    state.kill_switch_reason,
                    state.day,
                    state.day_start_equity,
                    state.last_equity,
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()
