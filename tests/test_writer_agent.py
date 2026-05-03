from __future__ import annotations

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, RDF, SKOS

from ontobridge.agents.governance import GovernanceAgent
from ontobridge.agents.relations import RelationsAgent
from ontobridge.agents.writer import WriterAgent
from ontobridge.models import (
    BusinessRule,
    CandidateLabel,
    EnrichedTerm,
    FIBOMatch,
    HarvestRecord,
    LifecycleStatus,
    MatchResult,
    MatchType,
    PlacementStatus,
    PolicyContext,
    SemanticRelation,
    SourceRef,
    SourceType,
    TaxonomyPlacement,
    Tier,
)
from ontobridge.publisher import InMemoryPublisher

REL_NS = "http://ontobridge.dev/ontology/bank/relations/"
BANK_NS = "http://ontobridge.dev/ontology/bank/"


# ----------------------- helpers -----------------------

def _harvest() -> HarvestRecord:
    return HarvestRecord(
        text="x",
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="ui"),
        tier=Tier.UNSTRUCTURED,
    )


_PREMIUM_DEFINITION = (
    "A retail customer who holds premium credit products with the bank and uses "
    "concierge channels for high-touch service."
)


def _enriched_premium_customer() -> EnrichedTerm:
    """A fully populated EnrichedTerm — Mapping/Taxonomy/Relations/Governance
    fields filled in directly so the test isolates the Writer."""
    t = EnrichedTerm.from_harvest(_harvest())
    t.candidate_labels = [
        CandidateLabel(text="Premium retail customer", confidence=0.95),
        CandidateLabel(text="Premium PI customer", confidence=0.7),
    ]
    t.definition = _PREMIUM_DEFINITION
    t.taxonomy_placement = TaxonomyPlacement(
        broader_concept_uri=f"{BANK_NS}RetailCustomer",
        scheme_uri=f"{BANK_NS}SchemeParty",
        domain_prefix="bank:PremiumRetailCustomer",
        status=PlacementStatus.PLACED,
    )
    t.fibo_match = FIBOMatch(
        uri="https://spec.edmcouncil.org/fibo/ontology/FND/Parties/Parties/PartyInRole",
        expected_definition=_PREMIUM_DEFINITION,  # alignment → Rule 12 inert
    )
    t.policy_context = [
        PolicyContext(
            paragraph="Premium retail customers are defined in section 4.2.",
            document_ref="CreditPolicy_v3.pdf",
            section="4.2",
        ),
    ]
    t.relations = [
        SemanticRelation(
            subject_uri=f"{BANK_NS}PremiumRetailCustomer",
            predicate_uri=f"{REL_NS}holds",
            inverse_predicate_uri=f"{REL_NS}heldBy",
            object_label="PI loan",  # exists in v0.1 ontology as altLabel
            verb="holds",
        ),
        SemanticRelation(
            subject_uri=f"{BANK_NS}PremiumRetailCustomer",
            predicate_uri=f"{REL_NS}uses",
            inverse_predicate_uri=f"{REL_NS}usedBy",
            object_label="some unmapped channel",  # won't resolve to a URI
            verb="uses",
        ),
    ]
    return t


def _govern(term: EnrichedTerm, base_ontology) -> EnrichedTerm:
    """Run the real GovernanceAgent so lifecycle mapping is exercised end-to-end."""
    from ontobridge.agents.governance import Candidate, PolicyRef

    cand = Candidate(
        preferred_label=term.preferred_label,
        domain=term.taxonomy_placement.scheme_uri if term.taxonomy_placement else None,
        definition=term.definition,
        policy_refs=[
            PolicyRef(document=p.document_ref, section=p.section)
            for p in term.policy_context
        ],
        fibo_match=term.fibo_match,
    )
    term.governance_result = GovernanceAgent(base_ontology).evaluate(cand)
    return term


# ----------------------- assembly -----------------------

def test_assemble_returns_published_term_with_turtle(base_ontology):
    pub = InMemoryPublisher()
    writer = WriterAgent(pub, ontology=base_ontology)
    term = _govern(_enriched_premium_customer(), base_ontology)
    published = writer.assemble(term, approved_by="steward.alice")
    assert published.term_uri == f"{BANK_NS}PremiumRetailCustomer"
    assert published.turtle is not None and published.turtle.strip()
    # Lifecycle comes from PublishedTerm.from_enriched (governance → publish).
    assert published.lifecycle_status is LifecycleStatus.PUBLISHED


def test_assemble_demotes_to_review_when_approver_missing(base_ontology):
    pub = InMemoryPublisher()
    writer = WriterAgent(pub, ontology=base_ontology)
    term = _govern(_enriched_premium_customer(), base_ontology)
    published = writer.assemble(term)  # no approver
    assert published.lifecycle_status is LifecycleStatus.REVIEW


def test_publish_pushes_through_publisher(base_ontology):
    pub = InMemoryPublisher()
    writer = WriterAgent(pub, ontology=base_ontology)
    term = _govern(_enriched_premium_customer(), base_ontology)
    published = writer.publish(term, approved_by="steward.alice")
    fetched = pub.get_term(published.term_uri)
    assert fetched.term_uri == published.term_uri
    assert fetched.turtle == published.turtle


# ----------------------- URI derivation -----------------------

def test_uri_from_taxonomy_placement_curie(base_ontology):
    pub = InMemoryPublisher()
    writer = WriterAgent(pub, ontology=base_ontology)
    term = _enriched_premium_customer()
    # taxonomy_placement.domain_prefix == "bank:PremiumRetailCustomer"
    assert writer._derive_uri(term) == f"{BANK_NS}PremiumRetailCustomer"


def test_uri_falls_back_to_camelcased_label(base_ontology):
    pub = InMemoryPublisher()
    writer = WriterAgent(pub, ontology=base_ontology)
    t = EnrichedTerm.from_harvest(_harvest())
    t.candidate_labels = [CandidateLabel(text="ATM withdrawal", confidence=0.9)]
    assert writer._derive_uri(t) == f"{BANK_NS}ATMWithdrawal"


def test_explicit_term_uri_overrides_derivation(base_ontology):
    pub = InMemoryPublisher()
    writer = WriterAgent(pub, ontology=base_ontology)
    term = _govern(_enriched_premium_customer(), base_ontology)
    published = writer.publish(term, term_uri=f"{BANK_NS}OverrideURI", approved_by="x")
    assert published.term_uri == f"{BANK_NS}OverrideURI"


# ----------------------- Turtle structure -----------------------

def _parse(published_term) -> Graph:
    g = Graph()
    g.parse(data=published_term.turtle, format="turtle")
    return g


def test_turtle_includes_concept_type(base_ontology):
    writer = WriterAgent(InMemoryPublisher(), ontology=base_ontology)
    published = writer.assemble(_govern(_enriched_premium_customer(), base_ontology))
    g = _parse(published)
    subj = URIRef(published.term_uri)
    assert (subj, RDF.type, SKOS.Concept) in g


def test_turtle_includes_pref_label_and_alt_labels(base_ontology):
    writer = WriterAgent(InMemoryPublisher(), ontology=base_ontology)
    published = writer.assemble(_govern(_enriched_premium_customer(), base_ontology))
    g = _parse(published)
    subj = URIRef(published.term_uri)
    pref_labels = list(g.objects(subj, SKOS.prefLabel))
    alt_labels = list(g.objects(subj, SKOS.altLabel))
    assert Literal("Premium retail customer", lang="en") in pref_labels
    assert Literal("Premium PI customer", lang="en") in alt_labels
    # The pref label must NOT be duplicated as an alt label.
    assert Literal("Premium retail customer", lang="en") not in alt_labels


def test_turtle_includes_definition(base_ontology):
    writer = WriterAgent(InMemoryPublisher(), ontology=base_ontology)
    published = writer.assemble(_govern(_enriched_premium_customer(), base_ontology))
    g = _parse(published)
    subj = URIRef(published.term_uri)
    defs = list(g.objects(subj, SKOS.definition))
    assert len(defs) == 1
    assert "premium credit products" in str(defs[0])


def test_turtle_includes_broader_and_in_scheme(base_ontology):
    writer = WriterAgent(InMemoryPublisher(), ontology=base_ontology)
    published = writer.assemble(_govern(_enriched_premium_customer(), base_ontology))
    g = _parse(published)
    subj = URIRef(published.term_uri)
    assert (subj, SKOS.broader, URIRef(f"{BANK_NS}RetailCustomer")) in g
    assert (subj, SKOS.inScheme, URIRef(f"{BANK_NS}SchemeParty")) in g


def test_turtle_includes_fibo_exact_match(base_ontology):
    writer = WriterAgent(InMemoryPublisher(), ontology=base_ontology)
    published = writer.assemble(_govern(_enriched_premium_customer(), base_ontology))
    g = _parse(published)
    subj = URIRef(published.term_uri)
    matches = list(g.objects(subj, SKOS.exactMatch))
    assert any("PartyInRole" in str(m) for m in matches)


def test_turtle_includes_dct_source_per_policy_ref(base_ontology):
    writer = WriterAgent(InMemoryPublisher(), ontology=base_ontology)
    published = writer.assemble(_govern(_enriched_premium_customer(), base_ontology))
    g = _parse(published)
    subj = URIRef(published.term_uri)
    sources = [str(s) for s in g.objects(subj, DCTERMS.source)]
    assert "policy:CreditPolicy_v3.pdf#section-4.2" in sources


def test_turtle_includes_resolved_relations_with_correct_predicate(base_ontology):
    writer = WriterAgent(InMemoryPublisher(), ontology=base_ontology)
    published = writer.assemble(_govern(_enriched_premium_customer(), base_ontology))
    g = _parse(published)
    subj = URIRef(published.term_uri)
    holds = URIRef(f"{REL_NS}holds")
    uses = URIRef(f"{REL_NS}uses")
    assert any(g.triples((subj, holds, None)))
    assert any(g.triples((subj, uses, None)))


def test_turtle_resolves_object_label_to_uri_when_in_ontology(base_ontology):
    writer = WriterAgent(InMemoryPublisher(), ontology=base_ontology)
    published = writer.assemble(_govern(_enriched_premium_customer(), base_ontology))
    g = _parse(published)
    subj = URIRef(published.term_uri)
    # "PI loan" is an altLabel of bank:PILoan in the v0.1 ontology — must resolve.
    pi_loan_uri = URIRef(f"{BANK_NS}PILoan")
    assert (subj, URIRef(f"{REL_NS}holds"), pi_loan_uri) in g


def test_turtle_emits_inverse_triple_when_object_resolves_to_uri(base_ontology):
    writer = WriterAgent(InMemoryPublisher(), ontology=base_ontology)
    published = writer.assemble(_govern(_enriched_premium_customer(), base_ontology))
    g = _parse(published)
    subj = URIRef(published.term_uri)
    pi_loan = URIRef(f"{BANK_NS}PILoan")
    held_by = URIRef(f"{REL_NS}heldBy")
    # Inverse: PILoan heldBy PremiumRetailCustomer
    assert (pi_loan, held_by, subj) in g


def test_turtle_uses_literal_for_unresolvable_object(base_ontology):
    writer = WriterAgent(InMemoryPublisher(), ontology=base_ontology)
    published = writer.assemble(_govern(_enriched_premium_customer(), base_ontology))
    g = _parse(published)
    subj = URIRef(published.term_uri)
    uses = URIRef(f"{REL_NS}uses")
    objects = list(g.objects(subj, uses))
    assert any(isinstance(o, Literal) and "unmapped channel" in str(o) for o in objects)


def test_turtle_skips_unresolved_verb_relations(base_ontology):
    """Relations flagged UNRESOLVED_VERB by the Relations agent must not leak
    into the published Turtle as triples (their predicate URI is None)."""
    from ontobridge.models import RelationStatus

    writer = WriterAgent(InMemoryPublisher(), ontology=base_ontology)
    term = _govern(_enriched_premium_customer(), base_ontology)
    term.relations.append(
        SemanticRelation(
            subject_uri=f"{BANK_NS}PremiumRetailCustomer",
            predicate_uri=None,
            inverse_predicate_uri=None,
            object_label="suspicious activity",
            verb="processes",
            confidence=0.3,
            status=RelationStatus.UNRESOLVED_VERB,
        )
    )
    published = writer.assemble(term)
    assert "processes" not in published.turtle
    assert "suspicious activity" not in published.turtle


def test_turtle_includes_editorial_note(base_ontology):
    writer = WriterAgent(InMemoryPublisher(), ontology=base_ontology)
    published = writer.assemble(_govern(_enriched_premium_customer(), base_ontology))
    assert "OntoBridge pipeline" in published.turtle


def test_turtle_is_round_trippable_via_rdflib(base_ontology):
    """Sanity check: the Writer's output parses back into rdflib without loss."""
    writer = WriterAgent(InMemoryPublisher(), ontology=base_ontology)
    published = writer.assemble(_govern(_enriched_premium_customer(), base_ontology))
    g = _parse(published)
    # At minimum we should round-trip prefLabel, definition, broader, inScheme,
    # exactMatch, one resolved relation, one inverse relation, and a source.
    assert len(g) >= 8


# ----------------------- ontology-less writer -----------------------

def test_writer_works_without_ontology(base_ontology):
    """Without an ontology the writer can't resolve object labels, but it should
    still emit prefLabel/definition/relations as literals."""
    pub = InMemoryPublisher()
    writer = WriterAgent(pub, ontology=None)
    term = _govern(_enriched_premium_customer(), base_ontology)
    published = writer.assemble(term)
    g = _parse(published)
    subj = URIRef(published.term_uri)
    # PI loan stays a literal because no ontology lookup is possible.
    holds = URIRef(f"{REL_NS}holds")
    objects = list(g.objects(subj, holds))
    assert any(isinstance(o, Literal) and "PI loan" in str(o) for o in objects)
