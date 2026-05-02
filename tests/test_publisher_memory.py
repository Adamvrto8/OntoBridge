from __future__ import annotations

import pytest

from ontobridge.models import (
    CandidateLabel,
    EnrichedTerm,
    HarvestRecord,
    LifecycleStatus,
    PublishedTerm,
    SourceRef,
    SourceType,
    Tier,
)
from ontobridge.publisher import (
    InMemoryPublisher,
    TermNotFoundError,
    TermPublisher,
)


def _term(uri: str, label: str = "Retail customer", definition: str | None = None) -> PublishedTerm:
    enriched = EnrichedTerm.from_harvest(
        HarvestRecord(
            text=definition or label,
            source_type=SourceType.USER_INPUT,
            source_ref=SourceRef(source_system="ui"),
            tier=Tier.UNSTRUCTURED,
        )
    )
    enriched.candidate_labels = [CandidateLabel(text=label, confidence=0.9)]
    enriched.definition = definition
    return PublishedTerm(
        enriched_term=enriched,
        term_uri=uri,
        lifecycle_status=LifecycleStatus.DRAFT,
    )


def test_in_memory_publisher_implements_abstract_interface():
    pub = InMemoryPublisher()
    assert isinstance(pub, TermPublisher)


def test_create_then_get_returns_equal_term():
    pub = InMemoryPublisher()
    term = _term("bank:Foo")
    pub.create_term(term)
    fetched = pub.get_term("bank:Foo")
    assert fetched.term_uri == "bank:Foo"
    assert fetched.lifecycle_status is LifecycleStatus.DRAFT


def test_create_term_returns_term_uri():
    pub = InMemoryPublisher()
    term = _term("bank:Foo")
    assert pub.create_term(term) == "bank:Foo"


def test_create_term_rejects_duplicate_uri():
    pub = InMemoryPublisher()
    pub.create_term(_term("bank:Foo"))
    with pytest.raises(ValueError, match="already exists"):
        pub.create_term(_term("bank:Foo"))


def test_get_term_raises_when_missing():
    pub = InMemoryPublisher()
    with pytest.raises(TermNotFoundError):
        pub.get_term("bank:DoesNotExist")


def test_update_term_increments_version():
    pub = InMemoryPublisher()
    pub.create_term(_term("bank:Foo", definition="v1"))
    updated = pub.update_term("bank:Foo", _term("bank:Foo", definition="v2"))
    assert updated.version == 2
    assert pub.get_term("bank:Foo").version == 2


def test_update_term_raises_when_missing():
    pub = InMemoryPublisher()
    with pytest.raises(TermNotFoundError):
        pub.update_term("bank:Missing", _term("bank:Missing"))


def test_search_by_label_substring():
    pub = InMemoryPublisher()
    pub.create_term(_term("bank:RetailCustomer", label="Retail customer"))
    pub.create_term(
        _term("bank:CorporateCustomer", label="Corporate customer", definition="biz")
    )
    pub.create_term(_term("bank:MobileApp", label="Mobile app"))
    results = pub.search_terms("customer")
    uris = sorted(r.term_uri for r in results)
    assert uris == ["bank:CorporateCustomer", "bank:RetailCustomer"]


def test_search_by_definition_substring():
    pub = InMemoryPublisher()
    pub.create_term(
        _term(
            "bank:Foo",
            label="Foo",
            definition="A FX hedging arrangement entered into with the bank.",
        )
    )
    results = pub.search_terms("hedging")
    assert len(results) == 1
    assert results[0].term_uri == "bank:Foo"


def test_search_empty_query_returns_all():
    pub = InMemoryPublisher()
    pub.create_term(_term("bank:A"))
    pub.create_term(_term("bank:B"))
    assert len(pub.search_terms("")) == 2


def test_transition_status_legal_path_draft_to_review():
    pub = InMemoryPublisher()
    pub.create_term(_term("bank:Foo"))
    transitioned = pub.transition_status("bank:Foo", LifecycleStatus.REVIEW)
    assert transitioned.lifecycle_status is LifecycleStatus.REVIEW


def test_transition_status_rejects_illegal_jump():
    pub = InMemoryPublisher()
    pub.create_term(_term("bank:Foo"))  # DRAFT
    with pytest.raises(ValueError, match="Illegal transition"):
        pub.transition_status("bank:Foo", LifecycleStatus.PUBLISHED)


def test_transition_status_to_self_is_noop():
    pub = InMemoryPublisher()
    pub.create_term(_term("bank:Foo"))
    pub.transition_status("bank:Foo", LifecycleStatus.DRAFT)
    assert pub.get_term("bank:Foo").lifecycle_status is LifecycleStatus.DRAFT


def test_transition_status_raises_when_missing():
    pub = InMemoryPublisher()
    with pytest.raises(TermNotFoundError):
        pub.transition_status("bank:Missing", LifecycleStatus.REVIEW)


def test_get_term_returns_a_copy_not_the_internal_object():
    pub = InMemoryPublisher()
    pub.create_term(_term("bank:Foo"))
    fetched = pub.get_term("bank:Foo")
    fetched.approved_by = "tampered"
    second = pub.get_term("bank:Foo")
    assert second.approved_by != "tampered"
