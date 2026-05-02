from __future__ import annotations

import pytest

from ontobridge.agents.governance import Candidate, GovernanceAgent, PolicyRef
from ontobridge.models import (
    BusinessRule,
    CandidateLabel,
    EnrichedTerm,
    FIBOMatch,
    HarvestRecord,
    MatchResult,
    MatchType,
    PolicyContext,
    RelationTriple,
    SourceRef,
    SourceType,
    TaxonomyPlacement,
    Tier,
    to_jsonable,
)

PARTY_SCHEME = "http://ontobridge.dev/ontology/bank/SchemeParty"


@pytest.fixture
def harvest_record() -> HarvestRecord:
    return HarvestRecord(
        text="A natural person who holds retail banking products for personal use.",
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(
            source_system="policy_repo",
            document_id="CreditPolicy_v3.pdf",
            section="2.1",
        ),
        confidence=0.92,
        tier=Tier.DOCUMENT,
    )


# ---- progressive enrichment ----

def test_enriched_term_starts_from_harvest(harvest_record):
    term = EnrichedTerm.from_harvest(harvest_record)
    assert term.harvest_record is harvest_record
    assert term.candidate_labels == []
    assert term.governance_result is None
    assert term.fibo_match is None


def test_progressive_enrichment_flow(harvest_record, base_ontology):
    term = EnrichedTerm.from_harvest(harvest_record)

    # NER agent
    term.candidate_labels = [
        CandidateLabel(text="Retail customer", confidence=0.92, ner_label="ORG"),
        CandidateLabel(text="customer", confidence=0.40),
    ]
    assert term.preferred_label == "Retail customer"

    # Policy linker
    term.policy_context = [
        PolicyContext(
            paragraph="Retail customers comprise individuals holding personal products.",
            document_ref="CreditPolicy_v3.pdf",
            section="2.1",
            similarity=0.81,
        ),
    ]

    # Mapping agent
    term.match_result = MatchResult(
        match_type=MatchType.DUPLICATE,
        similarity=1.0,
        target_uri="http://ontobridge.dev/ontology/bank/RetailCustomer",
    )

    # Taxonomy agent
    term.taxonomy_placement = TaxonomyPlacement(
        broader_concept_uri="http://ontobridge.dev/ontology/bank/Customer",
        scheme_uri=PARTY_SCHEME,
        domain_prefix="Retail_PI",
        placement_confidence=0.78,
    )

    # Definition agent
    term.definition = (
        "A natural person who holds retail banking products for personal or "
        "household use, served through the retail channel."
    )
    term.business_rules = [
        BusinessRule(rule_text="IF customer is individual THEN classify as retail."),
    ]

    # Relations agent
    term.relations = [
        RelationTriple(
            subject_uri="http://ontobridge.dev/ontology/bank/RetailCustomer",
            verb="uses",
            object_uri="http://ontobridge.dev/ontology/bank/MobileApp",
            inverse_verb="is used by",
        ),
    ]
    term.fibo_match = FIBOMatch(
        uri="https://spec.edmcouncil.org/fibo/ontology/FND/Parties/Parties/PartyInRole",
        expected_definition=(
            "A party acting in a particular role with respect to a thing or another "
            "party in a defined context."
        ),
    )

    # Governance agent — feed candidate built from this enriched term
    cand = Candidate(
        preferred_label=term.preferred_label,
        domain=PARTY_SCHEME,
        domain_code=term.taxonomy_placement.domain_prefix,
        definition=term.definition,
        policy_refs=[
            PolicyRef(document=p.document_ref, section=p.section)
            for p in term.policy_context
        ],
        fibo_match=term.fibo_match,
    )
    agent = GovernanceAgent(base_ontology)
    term.governance_result = agent.evaluate(cand)

    # Rule 1 (exact prefLabel duplicate) should fire
    assert term.governance_result.recommended_action == "block"
    assert term.governance_result.by_rule(1).triggered


# ---- validation ----

def test_candidate_label_rejects_empty_text():
    with pytest.raises(ValueError, match="text"):
        CandidateLabel(text="", confidence=0.5)


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_candidate_label_rejects_invalid_confidence(bad):
    with pytest.raises(ValueError, match="confidence"):
        CandidateLabel(text="x", confidence=bad)


def test_match_result_duplicate_requires_target_uri():
    with pytest.raises(ValueError, match="target_uri"):
        MatchResult(match_type=MatchType.DUPLICATE, similarity=1.0)


def test_match_result_new_does_not_require_target_uri():
    r = MatchResult(match_type=MatchType.NEW, similarity=0.0)
    assert r.target_uri is None


def test_policy_context_rejects_empty_paragraph():
    with pytest.raises(ValueError, match="paragraph"):
        PolicyContext(paragraph="", document_ref="x.pdf")


def test_relation_triple_rejects_empty_components():
    with pytest.raises(ValueError, match="verb"):
        RelationTriple(
            subject_uri="bank:A",
            verb="",
            object_uri="bank:B",
            inverse_verb="z",
        )


def test_taxonomy_placement_validates_uris():
    with pytest.raises(ValueError, match="broader_concept_uri"):
        TaxonomyPlacement(broader_concept_uri="", scheme_uri=PARTY_SCHEME)


# ---- serialization ----

def test_enriched_term_serializes_to_plain_dict(harvest_record):
    term = EnrichedTerm.from_harvest(harvest_record)
    term.candidate_labels = [CandidateLabel(text="Retail customer", confidence=0.9)]
    term.match_result = MatchResult(
        match_type=MatchType.FUZZY,
        similarity=0.85,
        target_uri="bank:RetailCustomer",
    )
    d = to_jsonable(term)
    assert d["candidate_labels"][0]["text"] == "Retail customer"
    assert d["match_result"]["match_type"] == "fuzzy"
    assert d["harvest_record"]["source_type"] == "policy_doc"
