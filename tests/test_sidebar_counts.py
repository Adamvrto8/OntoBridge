from __future__ import annotations

import pytest

from ontobridge.audit import AuditEntry, InMemoryAuditLog
from ontobridge.dashboard.app import sidebar_counts
from ontobridge.models.enrichment import CandidateLabel, EnrichedTerm
from ontobridge.models.enums import LifecycleStatus, SourceType
from ontobridge.models.published import PublishedTerm
from ontobridge.models.source import HarvestRecord, SourceRef
from ontobridge.publisher import InMemoryPublisher

_NS = "http://ontobridge.dev/ontology/bank/"


def _make_term(uri: str, label: str, status: LifecycleStatus) -> PublishedTerm:
    record = HarvestRecord(
        text=f"{label} is a banking term.",
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="test", document_id="doc1"),
    )
    enriched = EnrichedTerm(
        harvest_record=record,
        candidate_labels=[CandidateLabel(text=label, confidence=1.0)],
        definition=f"{label} definition.",
    )
    kwargs = {"enriched_term": enriched, "term_uri": uri, "lifecycle_status": status}
    if status is LifecycleStatus.PUBLISHED:
        kwargs["approved_by"] = "alice"
    return PublishedTerm(**kwargs)


def _pub(*pairs: tuple[str, LifecycleStatus]) -> InMemoryPublisher:
    pub = InMemoryPublisher()
    for i, (label, status) in enumerate(pairs):
        pub.create_term(_make_term(f"{_NS}{label}", label, status))
    return pub


def _log(*actions: str) -> InMemoryAuditLog:
    log = InMemoryAuditLog()
    for action in actions:
        log.record(AuditEntry(
            term_uri=f"{_NS}T",
            term_label="T",
            action=action,
            actor="alice",
            previous_status=LifecycleStatus.REVIEW,
            new_status=LifecycleStatus.PUBLISHED,
        ))
    return log


# ---------------------------------------------------------------------------
# sidebar_counts
# ---------------------------------------------------------------------------

def test_empty_publisher_and_log_returns_empty_dict():
    result = sidebar_counts(InMemoryPublisher(), InMemoryAuditLog())
    assert result == {}


def test_review_terms_appear_under_governance_inbox():
    pub = _pub(("Mortgage", LifecycleStatus.REVIEW), ("LTV", LifecycleStatus.REVIEW))
    result = sidebar_counts(pub, InMemoryAuditLog())
    assert result["Governance Inbox"] == 2


def test_published_terms_appear_under_glossary_browser():
    pub = _pub(("Mortgage", LifecycleStatus.PUBLISHED))
    result = sidebar_counts(pub, InMemoryAuditLog())
    assert result["Glossary Browser"] == 1


def test_audit_entries_appear_under_audit_log():
    result = sidebar_counts(InMemoryPublisher(), _log("approved", "rejected"))
    assert result["Audit Log"] == 2


def test_zero_counts_excluded_from_dict():
    pub = _pub(("Mortgage", LifecycleStatus.CANDIDATE))
    result = sidebar_counts(pub, InMemoryAuditLog())
    assert "Governance Inbox" not in result
    assert "Glossary Browser" not in result
    assert "Audit Log" not in result


def test_candidate_terms_not_counted():
    pub = _pub(
        ("Mortgage", LifecycleStatus.CANDIDATE),
        ("LTV", LifecycleStatus.DRAFT),
    )
    result = sidebar_counts(pub, InMemoryAuditLog())
    assert "Governance Inbox" not in result


def test_mixed_statuses_counted_correctly():
    pub = _pub(
        ("Mortgage", LifecycleStatus.REVIEW),
        ("LTV", LifecycleStatus.PUBLISHED),
        ("Collateral", LifecycleStatus.CANDIDATE),
        ("Overdraft", LifecycleStatus.REVIEW),
    )
    result = sidebar_counts(pub, _log("approved"))
    assert result["Governance Inbox"] == 2
    assert result["Glossary Browser"] == 1
    assert result["Audit Log"] == 1
