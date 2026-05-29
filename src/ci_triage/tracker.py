from __future__ import annotations

import sqlite3
import datetime
import contextlib
from pathlib import Path
from typing import Generator


_DDL = """
CREATE TABLE IF NOT EXISTS flaky_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    test_name   TEXT    NOT NULL,
    build_id    TEXT,
    source      TEXT    NOT NULL,
    failed_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_flaky_test ON flaky_events(test_name);
CREATE INDEX IF NOT EXISTS idx_flaky_time ON flaky_events(failed_at);
"""

_WINDOW_DAYS = 90


class FlakyTestTracker:
    """SQLite-backed flaky test recurrence tracker.

    Recurrence score = (failure count in window) / max(1, total builds in window).
    Score > 0.70 → quarantine candidate.
    """

    def __init__(self, db_path: str | Path = "~/.ci-triage/flaky.db") -> None:
        self._db = Path(db_path).expanduser()
        self._db.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_DDL)

    @contextlib.contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._db, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()

    def record(self, test_name: str, build_id: str | None, source: str) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO flaky_events(test_name, build_id, source, failed_at) VALUES (?,?,?,?)",
                (test_name, build_id, source, now),
            )

    def scores(self, test_names: list[str]) -> dict[str, float]:
        if not test_names:
            return {}
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=_WINDOW_DAYS)
        ).isoformat()
        placeholders = ",".join("?" for _ in test_names)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT test_name, COUNT(*) FROM flaky_events "
                f"WHERE test_name IN ({placeholders}) AND failed_at >= ? "
                f"GROUP BY test_name",
                (*test_names, cutoff),
            ).fetchall()
        counts = {name: count for name, count in rows}
        total_builds = self._total_builds_in_window(cutoff)
        return {
            name: min(1.0, counts.get(name, 0) / max(1, total_builds))
            for name in test_names
        }

    def _total_builds_in_window(self, cutoff: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT build_id) FROM flaky_events WHERE failed_at >= ?",
                (cutoff,),
            ).fetchone()
        return row[0] if row else 1

    def top_flaky(self, n: int = 10) -> list[tuple[str, float]]:
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=_WINDOW_DAYS)
        ).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT test_name, COUNT(*) as cnt FROM flaky_events "
                "WHERE failed_at >= ? GROUP BY test_name ORDER BY cnt DESC LIMIT ?",
                (cutoff, n),
            ).fetchall()
        total = self._total_builds_in_window(cutoff)
        return [(name, min(1.0, cnt / max(1, total))) for name, cnt in rows]
