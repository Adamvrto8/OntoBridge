from __future__ import annotations

from dataclasses import replace

import pytest

from ontobridge.models import (
    CandidateLabel,
    EnrichedTerm,
    HarvestRecord,
    LifecycleStatus,
    SourceRef,
    SourceType,
    Tier,
)
from ontobridge.models.published import PublishedTerm
from ontobridge.publisher import TermNotFoundError
from ontobridge.publisher.sqlite import SqlitePublisher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _harvest() -> HarvestRecord:
    return HarvestRecord(
        text="A retail customer who holds products for personal use at the bank.",
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="Policy.pdf"),
        tier=Tier.DOCUMENT,
    )


def _published_term(
    uri: str = "bank:RetailCustomer",
    label: str = "Retail customer",
    status: LifecycleStatus = LifecycleStatus.REVIEW,
    approved_by: str | None = None,
) -> PublishedTerm:
    enriched = EnrichedTerm.from_harvest(_harvest())
    enriched.candidate_labels = [CandidateLabel(text=label, confidence=0.95)]
    enriched.definition = _harvest().text
    return PublishedTerm(
        enriched_term=enriched,
        term_uri=uri,
        lifecycle_status=status,
        approved_by=approved_by,
    )


@pytest.fixture
def pub() -> SqlitePublisher:
    return SqlitePublisher(":memory:")


# ---------------------------------------------------------------------------
# Construction and schema
# ---------------------------------------------------------------------------

def test_in_memory_db_initialises_cleanly():
    pub = SqlitePublisher(":memory:")
    assert pub.count() == 0


def test_file_db_creates_file(tmp_path):
    db_file = tmp_path / "terms.db"
    assert not db_file.exists()
    SqlitePublisher(db_file)
    assert db_file.exists()


def test_file_db_persists_across_instances(tmp_path):
    db_file = tmp_path / "terms.db"
    pub_a = SqlitePublisher(db_file)
    pub_a.create_term(_published_term())

    pub_b = SqlitePublisher(db_file)
    assert pub_b.count() == 1
    fetched = pub_b.get_term("bank:RetailCustomer")
    assert fetched.term_uri == "bank:RetailCustomer"


# ---------------------------------------------------------------------------
# create_term
# ---------------------------------------------------------------------------

def test_create_term_returns_uri(pub):
    uri = pub.create_term(_published_term())
    assert uri == "bank:RetailCustomer"


def test_create_term_increments_count(pub):
    pub.create_term(_published_term("bank:A", "Term A"))
    pub.create_term(_published_term("bank:B", "Term B"))
    assert pub.count() == 2


def test_create_term_duplicate_raises(pub):
    pub.create_term(_published_term())
    with pytest.raises(ValueError, match="already exists"):
        pub.create_term(_published_term())


# ---------------------------------------------------------------------------
# get_term
# ---------------------------------------------------------------------------

def test_get_term_round_trips_full_object(pub):
    original = _published_term(approved_by="alice")
    pub.create_term(original)
    fetched = pub.get_term("bank:RetailCustomer")
    assert fetched.term_uri == original.term_uri
    assert fetched.lifecycle_status == original.lifecycle_status
    assert fetched.approved_by == original.approved_by
    assert fetched.enriched_term.preferred_label == original.enriched_term.preferred_label


def test_get_term_missing_raises(pub):
    with pytest.raises(TermNotFoundError):
        pub.get_term("bank:DoesNotExist")


def test_get_term_returns_independent_copy(pub):
    pub.create_term(_published_term())
    a = pub.get_term("bank:RetailCustomer")
    b = pub.get_term("bank:RetailCustomer")
    assert a is not b


# ---------------------------------------------------------------------------
# update_term
# ---------------------------------------------------------------------------

def test_update_term_bumps_version(pub):
    pub.create_term(_published_term())
    current = pub.get_term("bank:RetailCustomer")
    assert current.version == 1
    pub.update_term("bank:RetailCustomer", replace(current, approved_by="bob"))
    updated = pub.get_term("bank:RetailCustomer")
    assert updated.version == 2


def test_update_term_persists_changes(pub):
    pub.create_term(_published_term())
    current = pub.get_term("bank:RetailCustomer")
    pub.update_term("bank:RetailCustomer", replace(current, approved_by="carol"))
    assert pub.get_term("bank:RetailCustomer").approved_by == "carol"


def test_update_term_missing_raises(pub):
    with pytest.raises(TermNotFoundError):
        pub.update_term("bank:Ghost", _published_term())


# ---------------------------------------------------------------------------
# search_terms
# ---------------------------------------------------------------------------

def test_search_terms_empty_query_returns_all(pub):
    pub.create_term(_published_term("bank:A", "Alpha customer"))
    pub.create_term(_published_term("bank:B", "Beta account"))
    results = pub.search_terms("")
    assert len(results) == 2


def test_search_terms_matches_label(pub):
    pub.create_term(_published_term("bank:A", "Premium retail customer"))
    pub.create_term(_published_term("bank:B", "KYC verification process"))
    hits = pub.search_terms("premium")
    assert len(hits) == 1
    assert hits[0].term_uri == "bank:A"


def test_search_terms_matches_definition(pub):
    pub.create_term(_published_term("bank:A", "Term A"))
    hits = pub.search_terms("holds products for personal use")
    assert len(hits) == 1


def test_search_terms_case_insensitive(pub):
    pub.create_term(_published_term("bank:A", "Retail Customer"))
    assert len(pub.search_terms("RETAIL")) == 1
    assert len(pub.search_terms("retail")) == 1


def test_search_terms_no_match_returns_empty(pub):
    pub.create_term(_published_term())
    assert pub.search_terms("zzznomatch") == []


# ---------------------------------------------------------------------------
# transition_status
# ---------------------------------------------------------------------------

def test_transition_candidate_to_review(pub):
    pub.create_term(_published_term(status=LifecycleStatus.CANDIDATE))
    result = pub.transition_status("bank:RetailCustomer", LifecycleStatus.REVIEW)
    assert result.lifecycle_status == LifecycleStatus.REVIEW
    assert pub.get_term("bank:RetailCustomer").lifecycle_status == LifecycleStatus.REVIEW


def test_transition_review_to_published_requires_approved_by(pub):
    pub.create_term(_published_term(status=LifecycleStatus.REVIEW))
    with pytest.raises(ValueError, match="approved_by"):
        pub.transition_status("bank:RetailCustomer", LifecycleStatus.PUBLISHED)


def test_transition_review_to_published_with_approver(pub):
    pub.create_term(_published_term(status=LifecycleStatus.REVIEW, approved_by="alice"))
    result = pub.transition_status("bank:RetailCustomer", LifecycleStatus.PUBLISHED)
    assert result.lifecycle_status == LifecycleStatus.PUBLISHED


def test_illegal_transition_raises(pub):
    pub.create_term(_published_term(status=LifecycleStatus.CANDIDATE))
    with pytest.raises(ValueError, match="Illegal transition"):
        pub.transition_status("bank:RetailCustomer", LifecycleStatus.PUBLISHED)


def test_transition_missing_term_raises(pub):
    with pytest.raises(TermNotFoundError):
        pub.transition_status("bank:Ghost", LifecycleStatus.REVIEW)


# ---------------------------------------------------------------------------
# delete_term
# ---------------------------------------------------------------------------

def test_delete_term_removes_it(pub):
    pub.create_term(_published_term())
    pub.delete_term("bank:RetailCustomer")
    assert pub.count() == 0
    with pytest.raises(TermNotFoundError):
        pub.get_term("bank:RetailCustomer")


def test_delete_missing_term_raises(pub):
    with pytest.raises(TermNotFoundError):
        pub.delete_term("bank:Ghost")


# ---------------------------------------------------------------------------
# Pipeline integration — run a term through PipelineRunner into SqlitePublisher
# ---------------------------------------------------------------------------

def test_pipeline_runner_works_with_sqlite_publisher(base_ontology, tmp_path):
    from ontobridge.pipeline import PipelineRunner
    from ontobridge.models import PolicyContext

    db = tmp_path / "test.db"
    pub = SqlitePublisher(db)
    runner = PipelineRunner(base_ontology, pub)

    harvest = HarvestRecord(
        text="Governance test term.",
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="P.pdf"),
        tier=Tier.DOCUMENT,
    )
    term = EnrichedTerm.from_harvest(harvest)
    term.candidate_labels = [CandidateLabel(text="Premium retail customer", confidence=0.95)]
    term.definition = (
        "A retail customer who holds premium credit products with the bank "
        "and uses concierge channels for high-touch service."
    )
    term.policy_context = [
        PolicyContext(paragraph=term.definition, document_ref="P.pdf", section="4.2")
    ]

    published = runner.run(term, approved_by="alice")

    # Term is in the SQLite db, survives a new publisher instance on same file
    pub2 = SqlitePublisher(db)
    fetched = pub2.get_term(published.term_uri)
    assert fetched.enriched_term.preferred_label == "Premium retail customer"
    assert fetched.turtle and "skos:prefLabel" in fetched.turtle
