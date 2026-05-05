from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ontobridge.audit import AuditEntry, InMemoryAuditLog, SqliteAuditLog
from ontobridge.models.enums import LifecycleStatus

_URI_A = "http://ontobridge.dev/ontology/bank/Mortgage"
_URI_B = "http://ontobridge.dev/ontology/bank/LTV"


def _entry(
    term_uri: str = _URI_A,
    term_label: str = "Mortgage",
    action: str = "approved",
    actor: str = "alice",
    previous: LifecycleStatus = LifecycleStatus.REVIEW,
    new: LifecycleStatus = LifecycleStatus.PUBLISHED,
) -> AuditEntry:
    return AuditEntry(
        term_uri=term_uri,
        term_label=term_label,
        action=action,
        actor=actor,
        previous_status=previous,
        new_status=new,
    )


# ---------------------------------------------------------------------------
# AuditEntry model
# ---------------------------------------------------------------------------

def test_entry_id_auto_generated():
    e = _entry()
    assert e.entry_id and len(e.entry_id) == 16


def test_entry_id_stable_for_same_inputs():
    e1 = AuditEntry(
        term_uri=_URI_A,
        term_label="Mortgage",
        action="approved",
        actor="alice",
        previous_status=LifecycleStatus.REVIEW,
        new_status=LifecycleStatus.PUBLISHED,
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    e2 = AuditEntry(
        term_uri=_URI_A,
        term_label="Mortgage",
        action="approved",
        actor="alice",
        previous_status=LifecycleStatus.REVIEW,
        new_status=LifecycleStatus.PUBLISHED,
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert e1.entry_id == e2.entry_id


def test_entry_rejects_empty_term_uri():
    with pytest.raises(ValueError):
        AuditEntry(
            term_uri="",
            term_label="X",
            action="approved",
            actor="alice",
            previous_status=LifecycleStatus.REVIEW,
            new_status=LifecycleStatus.PUBLISHED,
        )


# ---------------------------------------------------------------------------
# InMemoryAuditLog
# ---------------------------------------------------------------------------

def test_in_memory_starts_empty():
    log = InMemoryAuditLog()
    assert log.count() == 0
    assert log.entries() == []


def test_in_memory_record_and_count():
    log = InMemoryAuditLog()
    log.record(_entry())
    assert log.count() == 1


def test_in_memory_entries_returned():
    log = InMemoryAuditLog()
    e = _entry()
    log.record(e)
    result = log.entries()
    assert len(result) == 1
    assert result[0].entry_id == e.entry_id


def test_in_memory_filter_by_term_uri():
    log = InMemoryAuditLog()
    log.record(_entry(term_uri=_URI_A))
    log.record(_entry(term_uri=_URI_B, term_label="LTV"))
    result = log.entries(term_uri=_URI_A)
    assert len(result) == 1
    assert result[0].term_uri == _URI_A


def test_in_memory_filter_by_actor():
    log = InMemoryAuditLog()
    log.record(_entry(actor="alice"))
    log.record(_entry(actor="bob"))
    result = log.entries(actor="alice")
    assert len(result) == 1
    assert result[0].actor == "alice"


def test_in_memory_limit():
    log = InMemoryAuditLog()
    for _ in range(5):
        log.record(_entry())
    assert len(log.entries(limit=3)) == 3


def test_in_memory_newest_first():
    log = InMemoryAuditLog()
    e1 = AuditEntry(
        term_uri=_URI_A, term_label="Mortgage", action="approved", actor="alice",
        previous_status=LifecycleStatus.REVIEW, new_status=LifecycleStatus.PUBLISHED,
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    e2 = AuditEntry(
        term_uri=_URI_A, term_label="Mortgage", action="rejected", actor="bob",
        previous_status=LifecycleStatus.REVIEW, new_status=LifecycleStatus.CANDIDATE,
        timestamp=datetime(2025, 6, 1, tzinfo=timezone.utc),
    )
    log.record(e1)
    log.record(e2)
    result = log.entries()
    assert result[0].timestamp > result[1].timestamp


# ---------------------------------------------------------------------------
# SqliteAuditLog
# ---------------------------------------------------------------------------

def test_sqlite_starts_empty(tmp_path):
    log = SqliteAuditLog(tmp_path / "audit.db")
    assert log.count() == 0


def test_sqlite_record_and_count(tmp_path):
    log = SqliteAuditLog(tmp_path / "audit.db")
    log.record(_entry())
    assert log.count() == 1


def test_sqlite_persists_across_instances(tmp_path):
    db = tmp_path / "audit.db"
    log1 = SqliteAuditLog(db)
    log1.record(_entry())

    log2 = SqliteAuditLog(db)
    assert log2.count() == 1
    result = log2.entries()
    assert result[0].action == "approved"
    assert result[0].actor == "alice"


def test_sqlite_filter_by_term_uri(tmp_path):
    log = SqliteAuditLog(tmp_path / "audit.db")
    log.record(_entry(term_uri=_URI_A))
    log.record(_entry(term_uri=_URI_B, term_label="LTV"))
    result = log.entries(term_uri=_URI_A)
    assert len(result) == 1
    assert result[0].term_uri == _URI_A


def test_sqlite_filter_by_actor(tmp_path):
    log = SqliteAuditLog(tmp_path / "audit.db")
    log.record(_entry(actor="alice"))
    log.record(_entry(actor="bob"))
    result = log.entries(actor="bob")
    assert len(result) == 1
    assert result[0].actor == "bob"


def test_sqlite_newest_first(tmp_path):
    log = SqliteAuditLog(tmp_path / "audit.db")
    e1 = AuditEntry(
        term_uri=_URI_A, term_label="Mortgage", action="approved", actor="alice",
        previous_status=LifecycleStatus.REVIEW, new_status=LifecycleStatus.PUBLISHED,
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    e2 = AuditEntry(
        term_uri=_URI_A, term_label="Mortgage", action="rejected", actor="bob",
        previous_status=LifecycleStatus.REVIEW, new_status=LifecycleStatus.CANDIDATE,
        timestamp=datetime(2025, 6, 1, tzinfo=timezone.utc),
    )
    log.record(e1)
    log.record(e2)
    result = log.entries()
    assert result[0].timestamp > result[1].timestamp


def test_sqlite_roundtrip_all_fields(tmp_path):
    log = SqliteAuditLog(tmp_path / "audit.db")
    e = AuditEntry(
        term_uri=_URI_A,
        term_label="Mortgage",
        action="sent_to_draft",
        actor="carol",
        previous_status=LifecycleStatus.REVIEW,
        new_status=LifecycleStatus.DRAFT,
        timestamp=datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
        comment="Needs more evidence",
    )
    log.record(e)
    result = log.entries()[0]
    assert result.term_uri == e.term_uri
    assert result.term_label == e.term_label
    assert result.action == e.action
    assert result.actor == e.actor
    assert result.previous_status == e.previous_status
    assert result.new_status == e.new_status
    assert result.comment == e.comment
