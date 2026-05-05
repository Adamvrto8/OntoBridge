from __future__ import annotations

import pickle
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from ontobridge.models.enums import LifecycleStatus
from ontobridge.models.published import PublishedTerm
from ontobridge.publisher.base import TermNotFoundError, TermPublisher
from ontobridge.publisher.memory import ALLOWED_TRANSITIONS

_DDL = """
CREATE TABLE IF NOT EXISTS terms (
    term_uri      TEXT PRIMARY KEY,
    lifecycle     TEXT NOT NULL,
    search_text   TEXT NOT NULL,
    data          BLOB NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lifecycle ON terms (lifecycle);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _search_text(term: PublishedTerm) -> str:
    parts: list[str] = [term.term_uri]
    for cl in term.enriched_term.candidate_labels:
        parts.append(cl.text)
    if term.enriched_term.definition:
        parts.append(term.enriched_term.definition)
    return " ".join(parts).casefold()


class SqlitePublisher(TermPublisher):
    """Persistent TermPublisher backed by a local SQLite database.

    Uses Python's built-in ``sqlite3`` module — no extra dependencies.
    Terms are stored as pickle blobs so the full nested model graph is
    preserved without a custom deserializer.  A ``search_text`` column
    holds lowercased label + definition text for efficient substring search.

    Thread safety: WAL journal mode + a new connection per operation makes
    this safe for Streamlit's multi-thread model without explicit locking.

    Args:
        db_path: Path to the ``.db`` file.  Created automatically if it
            does not exist.  Pass ``":memory:"`` for an in-process
            database useful in tests.
    """

    def __init__(self, db_path: Path | str = "ontobridge.db") -> None:
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._init_db()

    # ------------------------------------------------------------------
    # TermPublisher interface
    # ------------------------------------------------------------------

    def create_term(self, term: PublishedTerm) -> str:
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT 1 FROM terms WHERE term_uri = ?", (term.term_uri,)
            ).fetchone()
            if existing:
                raise ValueError(
                    f"Term with URI {term.term_uri!r} already exists; use update_term"
                )
            now = _utc_now()
            conn.execute(
                "INSERT INTO terms (term_uri, lifecycle, search_text, data, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    term.term_uri,
                    term.lifecycle_status.value,
                    _search_text(term),
                    pickle.dumps(term),
                    now,
                    now,
                ),
            )
        return term.term_uri

    def update_term(self, term_id: str, term: PublishedTerm) -> PublishedTerm:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM terms WHERE term_uri = ?", (term_id,)
            ).fetchone()
            if row is None:
                raise TermNotFoundError(term_id)
            existing: PublishedTerm = pickle.loads(row[0])
            updated = replace(
                term,
                term_uri=term_id,
                version=existing.version + 1,
            )
            conn.execute(
                "UPDATE terms SET lifecycle=?, search_text=?, data=?, updated_at=? "
                "WHERE term_uri=?",
                (
                    updated.lifecycle_status.value,
                    _search_text(updated),
                    pickle.dumps(updated),
                    _utc_now(),
                    term_id,
                ),
            )
        return updated

    def get_term(self, term_id: str) -> PublishedTerm:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM terms WHERE term_uri = ?", (term_id,)
            ).fetchone()
        if row is None:
            raise TermNotFoundError(term_id)
        return pickle.loads(row[0])

    def search_terms(self, query: str) -> list[PublishedTerm]:
        with self._conn() as conn:
            if not query:
                rows = conn.execute("SELECT data FROM terms").fetchall()
            else:
                needle = f"%{query.casefold()}%"
                rows = conn.execute(
                    "SELECT data FROM terms WHERE search_text LIKE ?", (needle,)
                ).fetchall()
        return [pickle.loads(row[0]) for row in rows]

    def transition_status(
        self, term_id: str, new_status: LifecycleStatus
    ) -> PublishedTerm:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM terms WHERE term_uri = ?", (term_id,)
            ).fetchone()
            if row is None:
                raise TermNotFoundError(term_id)
            existing: PublishedTerm = pickle.loads(row[0])
            allowed = ALLOWED_TRANSITIONS[existing.lifecycle_status]
            if new_status not in allowed and new_status is not existing.lifecycle_status:
                raise ValueError(
                    f"Illegal transition {existing.lifecycle_status.value} → "
                    f"{new_status.value} for term {term_id!r}"
                )
            updated = replace(existing, lifecycle_status=new_status)
            conn.execute(
                "UPDATE terms SET lifecycle=?, data=?, updated_at=? WHERE term_uri=?",
                (new_status.value, pickle.dumps(updated), _utc_now(), term_id),
            )
        return updated

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Return total number of stored terms."""
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM terms").fetchone()
        return row[0]

    def delete_term(self, term_id: str) -> None:
        """Permanently remove a term.  Raises TermNotFoundError if absent."""
        with self._conn() as conn:
            result = conn.execute(
                "DELETE FROM terms WHERE term_uri = ?", (term_id,)
            )
            if result.rowcount == 0:
                raise TermNotFoundError(term_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        self._connection.executescript(_DDL)
        self._connection.commit()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        with self._lock:
            try:
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
