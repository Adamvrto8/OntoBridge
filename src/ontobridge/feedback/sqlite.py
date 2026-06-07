from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ontobridge.feedback.base import FeedbackStore
from ontobridge.feedback.models import FeedbackEvent

_DDL = """
CREATE TABLE IF NOT EXISTS feedback_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    term_uri   TEXT NOT NULL,
    term_label TEXT NOT NULL,
    old_value  TEXT NOT NULL,
    new_value  TEXT NOT NULL,
    actor      TEXT NOT NULL,
    timestamp  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_event_type ON feedback_events (event_type);
"""


class SqliteFeedbackStore(FeedbackStore):
    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)
        with self._connect() as conn:
            conn.executescript(_DDL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def record(self, event: FeedbackEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO feedback_events "
                "(event_type, term_uri, term_label, old_value, new_value, actor, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event.event_type,
                    event.term_uri,
                    event.term_label,
                    event.old_value,
                    event.new_value,
                    event.actor,
                    event.timestamp.isoformat(),
                ),
            )

    def get_examples(self, event_type: str, limit: int = 5) -> list[FeedbackEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_type, term_uri, term_label, old_value, new_value, actor, timestamp "
                "FROM feedback_events WHERE event_type = ? ORDER BY id DESC LIMIT ?",
                (event_type, limit),
            ).fetchall()
        return [
            FeedbackEvent(
                event_type=row[0],
                term_uri=row[1],
                term_label=row[2],
                old_value=row[3],
                new_value=row[4],
                actor=row[5],
                timestamp=datetime.fromisoformat(row[6]),
            )
            for row in reversed(rows)
        ]
