from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from ontobridge.audit.base import AuditLog
from ontobridge.audit.models import AuditEntry
from ontobridge.models.enums import LifecycleStatus

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS audit_entries (
    entry_id        TEXT PRIMARY KEY,
    term_uri        TEXT NOT NULL,
    term_label      TEXT NOT NULL,
    action          TEXT NOT NULL,
    actor           TEXT NOT NULL,
    previous_status TEXT NOT NULL,
    new_status      TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    comment         TEXT
)
"""


class SqliteAuditLog(AuditLog):
    def __init__(self, db_path: str | Path) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    def record(self, entry: AuditEntry) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO audit_entries
                (entry_id, term_uri, term_label, action, actor,
                 previous_status, new_status, timestamp, comment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.entry_id,
                    entry.term_uri,
                    entry.term_label,
                    entry.action,
                    entry.actor,
                    entry.previous_status.value,
                    entry.new_status.value,
                    entry.timestamp.isoformat(),
                    entry.comment,
                ),
            )
            self._conn.commit()

    def entries(
        self,
        *,
        term_uri: str | None = None,
        actor: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        clauses: list[str] = []
        params: list[object] = []
        if term_uri is not None:
            clauses.append("term_uri = ?")
            params.append(term_uri)
        if actor is not None:
            clauses.append("actor = ?")
            params.append(actor)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT entry_id, term_uri, term_label, action, actor, "
                f"previous_status, new_status, timestamp, comment "
                f"FROM audit_entries {where} ORDER BY timestamp DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def count(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM audit_entries"
            ).fetchone()[0]

    @staticmethod
    def _row_to_entry(row: tuple) -> AuditEntry:
        entry_id, term_uri, term_label, action, actor, prev, new, ts, comment = row
        return AuditEntry(
            entry_id=entry_id,
            term_uri=term_uri,
            term_label=term_label,
            action=action,
            actor=actor,
            previous_status=LifecycleStatus(prev),
            new_status=LifecycleStatus(new),
            timestamp=datetime.fromisoformat(ts),
            comment=comment,
        )
