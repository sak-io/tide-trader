"""Append-only history of accepted trade signals.

Not a mutable queue: `create()` always inserts a new row, so buy and sell signals
for the same symbol both persist as separate rows over time - this is what makes
the CSV export meaningful as a hypothetical-performance log. `dedupe_key` only
gates the scan loop from re-firing the same symbol+direction twice in a calendar
day (via `exists_for_today`); it never deletes or collapses rows. `dismiss()` only
flips status - the row stays forever.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.models.domain import (
    IndicatorSnapshot,
    PerformanceSummary,
    Signal,
    SignalDirection,
    SignalSource,
    Suggestion,
    SuggestionOutcome,
    SuggestionStatus,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    price REAL NOT NULL,
    score REAL NOT NULL,
    indicators_json TEXT NOT NULL,
    triggered_rules_json TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    rationale TEXT,
    status TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    dedupe_key TEXT NOT NULL
)
"""

# Columns added after the first release; applied to pre-existing databases on startup.
_MIGRATION_COLUMNS = {
    "stop_price": "REAL",
    "target_price": "REAL",
    "outcome": "TEXT NOT NULL DEFAULT 'open'",
    "outcome_price": "REAL",
    "outcome_at": "TEXT",
    "last_price": "REAL",
}

_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_suggestions_symbol_generated_at "
    "ON suggestions (symbol, generated_at)"
)

# A fixed, hardcoded column list - never built from user/request input. bandit's
# B608 heuristically flags any f-string/concatenation containing a SQL keyword
# regardless of what's interpolated, so the two usages below carry a `# nosec B608`
# with this same justification; every value that actually varies still goes through
# a `?` placeholder and the sqlite3 parameter tuple, never string interpolation.
_SELECT_COLUMNS = (
    "id, symbol, direction, price, score, indicators_json, triggered_rules_json, "
    "sources_json, rationale, status, generated_at, updated_at, "
    "stop_price, target_price, outcome, outcome_price, outcome_at, last_price"
)


def return_pct(direction: SignalDirection, entry: float, price: float) -> float:
    change = (price - entry) / entry * 100
    return change if direction == SignalDirection.bullish else -change


def dedupe_key(symbol: str, direction: str, day: str) -> str:
    return f"{symbol.strip().upper()}:{direction}:{day}"


class SuggestionStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        parent = Path(self.db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
            conn.execute(_SCHEMA)
            existing = {row[1] for row in conn.execute("PRAGMA table_info(suggestions)")}
            for column, ddl in _MIGRATION_COLUMNS.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE suggestions ADD COLUMN {column} {ddl}")  # nosec B608
            conn.execute(_INDEX)
            conn.commit()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def exists_for_today(self, symbol: str, direction: str, today: str | None = None) -> bool:
        day = today or datetime.now(UTC).date().isoformat()
        key = dedupe_key(symbol, direction, day)
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM suggestions WHERE dedupe_key = ?", (key,)).fetchone()
        return row is not None

    def create(self, signal: Signal, rationale: str | None) -> Suggestion:
        now = datetime.now(UTC).isoformat()
        day = signal.generated_at.date().isoformat()
        key = dedupe_key(signal.symbol, signal.direction.value, day)

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO suggestions (
                    symbol, direction, price, score, indicators_json, triggered_rules_json,
                    sources_json, rationale, status, generated_at, updated_at, dedupe_key,
                    stop_price, target_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.symbol,
                    signal.direction.value,
                    signal.price,
                    signal.score,
                    signal.indicators.model_dump_json(),
                    json.dumps(signal.triggered_rules),
                    json.dumps([source.value for source in signal.sources]),
                    rationale,
                    SuggestionStatus.pending.value,
                    signal.generated_at.isoformat(),
                    now,
                    key,
                    signal.stop_price,
                    signal.target_price,
                ),
            )
            conn.commit()
            row_id = cursor.lastrowid

        suggestion = self._get(row_id)
        if suggestion is None:  # pragma: no cover - the row we just inserted always exists
            raise RuntimeError(f"Suggestion row {row_id} vanished immediately after insert.")
        return suggestion

    def _get(self, suggestion_id: int) -> Suggestion | None:
        query = f"SELECT {_SELECT_COLUMNS} FROM suggestions WHERE id = ?"  # nosec B608
        with self._connect() as conn:
            row = conn.execute(query, (suggestion_id,)).fetchone()
        return self._row_to_suggestion(row) if row is not None else None

    @staticmethod
    def _row_to_suggestion(row: tuple) -> Suggestion:
        (
            row_id,
            symbol,
            direction,
            price,
            score,
            indicators_json,
            triggered_rules_json,
            sources_json,
            rationale,
            status,
            generated_at,
            updated_at,
            stop_price,
            target_price,
            outcome,
            outcome_price,
            outcome_at,
            last_price,
        ) = row
        mark = outcome_price if outcome_price is not None else last_price
        return Suggestion(
            id=row_id,
            symbol=symbol,
            direction=direction,
            price=price,
            score=score,
            indicators=IndicatorSnapshot.model_validate_json(indicators_json),
            triggered_rules=json.loads(triggered_rules_json),
            sources=[SignalSource(source) for source in json.loads(sources_json)],
            rationale=rationale,
            status=status,
            generated_at=generated_at,
            updated_at=updated_at,
            stop_price=stop_price,
            target_price=target_price,
            outcome=outcome,
            outcome_price=outcome_price,
            outcome_at=outcome_at,
            last_price=last_price,
            return_pct=return_pct(SignalDirection(direction), price, mark) if mark is not None else None,
        )

    def list_pending(self) -> list[Suggestion]:
        return self.list_all(status=SuggestionStatus.pending)

    def list_all(
        self,
        symbol: str | None = None,
        status: SuggestionStatus | None = None,
        since: datetime | None = None,
    ) -> list[Suggestion]:
        query = f"SELECT {_SELECT_COLUMNS} FROM suggestions"  # nosec B608
        clauses = []
        params: list[str] = []
        if symbol is not None:
            clauses.append("symbol = ?")
            params.append(symbol.strip().upper())
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if since is not None:
            clauses.append("generated_at >= ?")
            params.append(since.isoformat())
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY generated_at ASC, id ASC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_suggestion(row) for row in rows]

    def list_open(self) -> list[Suggestion]:
        query = f"SELECT {_SELECT_COLUMNS} FROM suggestions WHERE outcome = ? ORDER BY id"  # nosec B608
        with self._connect() as conn:
            rows = conn.execute(query, (SuggestionOutcome.open.value,)).fetchall()
        return [self._row_to_suggestion(row) for row in rows]

    def record_outcome(
        self,
        suggestion_id: int,
        outcome: SuggestionOutcome,
        outcome_price: float | None,
        outcome_at: datetime | None,
        last_price: float | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE suggestions SET outcome = ?, outcome_price = ?, outcome_at = ?, last_price = ? "
                "WHERE id = ?",
                (
                    outcome.value,
                    outcome_price,
                    outcome_at.isoformat() if outcome_at else None,
                    last_price,
                    suggestion_id,
                ),
            )
            conn.commit()

    def performance(self) -> PerformanceSummary:
        rows = self.list_all()
        counts = {o: sum(1 for r in rows if r.outcome == o) for o in SuggestionOutcome}
        closed = [r for r in rows if r.outcome != SuggestionOutcome.open and r.return_pct is not None]
        wins = sum(1 for r in closed if r.return_pct > 0)
        return PerformanceSummary(
            total=len(rows),
            open=counts[SuggestionOutcome.open],
            target_hit=counts[SuggestionOutcome.target_hit],
            stopped=counts[SuggestionOutcome.stopped],
            expired=counts[SuggestionOutcome.expired],
            win_rate_pct=wins / len(closed) * 100 if closed else None,
            avg_return_pct=sum(r.return_pct for r in closed) / len(closed) if closed else None,
        )

    def dismiss(self, suggestion_id: int) -> Suggestion | None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE suggestions SET status = ?, updated_at = ? WHERE id = ?",
                (SuggestionStatus.dismissed.value, now, suggestion_id),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
        return self._get(suggestion_id)
