from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ontobridge.agents.governance import (
    Candidate,
    GovernanceAgent,
    PolicyRef,
)
from ontobridge.models import (
    EnrichedTerm,
    HarvestRecord,
    LifecycleStatus,
    PublishedTerm,
    SourceRef,
    SourceType,
    Tier,
    lifecycle_from_action,
    to_jsonable,
)

PARTY_SCHEME = "http://ontobridge.dev/ontology/bank/SchemeParty"
PROCESS_SCHEME = "http://ontobridge.dev/ontology/bank/SchemeProcess"


def _harvest() -> HarvestRecord:
    return HarvestRecord(
        text="A standing order mandate authorising recurring debits.",
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(
            source_system="policy_repo",
            document_id="PaymentsPolicy_v2.pdf",
            section="4.3",
        ),
        tier=Tier.DOCUMENT,
    )


# ---- lifecycle_from_action mapping ----

@pytest.mark.parametrize(
    "action,expected",
    [
        ("block", LifecycleStatus.CANDIDATE),
        ("draft", LifecycleStatus.DRAFT),
        ("review", LifecycleStatus.REVIEW),
        ("publish", LifecycleStatus.PUBLISHED),
    ],
)
def test_lifecycle_mapping(action, expected):
    assert lifecycle_from_action(action) is expected


def test_lifecycle_mapping_rejects_unknown_action():
    with pytest.raises(ValueError, match="Unknown recommended_action"):
        lifecycle_from_action("escalate")


# ---- PublishedTerm.from_enriched ----

def test_from_enriched_with_no_governance_defaults_to_candidate():
    enriched = EnrichedTerm.from_harvest(_harvest())
    pt = PublishedTerm.from_enriched(enriched, term_uri="bank:Foo")
    assert pt.lifecycle_status is LifecycleStatus.CANDIDATE


def test_from_enriched_publishes_when_governance_says_publish_and_approver_set(
    base_ontology,
):
    enriched = EnrichedTerm.from_harvest(_harvest())
    cand = Candidate(
        preferred_label="Standing order mandate",
        domain=PROCESS_SCHEME,
        definition=(
            "A recurring payment instruction issued by a customer authorising the bank "
            "to debit a fixed amount on a defined schedule."
        ),
        policy_refs=[PolicyRef(document="PaymentsPolicy_v2.pdf")],
    )
    enriched.governance_result = GovernanceAgent(base_ontology).evaluate(cand)
    assert enriched.governance_result.recommended_action == "publish"
    pt = PublishedTerm.from_enriched(
        enriched,
        term_uri="bank:StandingOrderMandate",
        approved_by="steward.alice",
        published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    assert pt.lifecycle_status is LifecycleStatus.PUBLISHED
    assert pt.approved_by == "steward.alice"
    assert pt.version == 1


def test_from_enriched_demotes_to_review_when_publish_lacks_approver(base_ontology):
    enriched = EnrichedTerm.from_harvest(_harvest())
    cand = Candidate(
        preferred_label="Standing order mandate",
        domain=PROCESS_SCHEME,
        definition=(
            "A recurring payment instruction issued by a customer authorising the bank "
            "to debit a fixed amount on a defined schedule."
        ),
        policy_refs=[PolicyRef(document="PaymentsPolicy_v2.pdf")],
    )
    enriched.governance_result = GovernanceAgent(base_ontology).evaluate(cand)
    pt = PublishedTerm.from_enriched(enriched, term_uri="bank:StandingOrderMandate")
    assert pt.lifecycle_status is LifecycleStatus.REVIEW


def test_from_enriched_blocks_to_candidate(base_ontology):
    enriched = EnrichedTerm.from_harvest(_harvest())
    cand = Candidate(
        preferred_label="Retail customer",
        domain=PARTY_SCHEME,
        definition=(
            "A natural person who holds retail banking products for personal use."
        ),
        policy_refs=[PolicyRef(document="CreditPolicy_v3.pdf")],
    )
    enriched.governance_result = GovernanceAgent(base_ontology).evaluate(cand)
    assert enriched.governance_result.recommended_action == "block"
    pt = PublishedTerm.from_enriched(enriched, term_uri="bank:RetailCustomer.Dup")
    assert pt.lifecycle_status is LifecycleStatus.CANDIDATE


# ---- direct constructor validation ----

def test_published_term_requires_term_uri():
    enriched = EnrichedTerm.from_harvest(_harvest())
    with pytest.raises(ValueError, match="term_uri"):
        PublishedTerm(enriched_term=enriched, term_uri="")


def test_published_term_published_status_requires_approver():
    enriched = EnrichedTerm.from_harvest(_harvest())
    with pytest.raises(ValueError, match="approved_by"):
        PublishedTerm(
            enriched_term=enriched,
            term_uri="bank:Foo",
            lifecycle_status=LifecycleStatus.PUBLISHED,
        )


def test_published_term_rejects_zero_version():
    enriched = EnrichedTerm.from_harvest(_harvest())
    with pytest.raises(ValueError, match="version"):
        PublishedTerm(enriched_term=enriched, term_uri="bank:Foo", version=0)


def test_published_term_serializes_with_lifecycle_value():
    enriched = EnrichedTerm.from_harvest(_harvest())
    pt = PublishedTerm(
        enriched_term=enriched,
        term_uri="bank:Foo",
        lifecycle_status=LifecycleStatus.DRAFT,
    )
    d = to_jsonable(pt)
    assert d["lifecycle_status"] == "draft"
    assert d["term_uri"] == "bank:Foo"
    assert d["version"] == 1
