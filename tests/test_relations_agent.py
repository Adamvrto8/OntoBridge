from __future__ import annotations

import pytest

from ontobridge.agents.relations import (
    InverseVerbLexicon,
    RegexHeuristicExtractor,
    RelationsAgent,
    SVOExtractor,
    SVOTriple,
)
from ontobridge.models import (
    CandidateLabel,
    EnrichedTerm,
    HarvestRecord,
    MatchResult,
    MatchType,
    PolicyContext,
    RelationStatus,
    SourceRef,
    SourceType,
    Tier,
)

REL_NS = "http://ontobridge.dev/ontology/bank/relations/"
RETAIL_CUSTOMER_URI = "http://ontobridge.dev/ontology/bank/RetailCustomer"


def _term(
    label: str = "Retail customer",
    definition: str | None = None,
    target_uri: str | None = RETAIL_CUSTOMER_URI,
    policy_paragraphs: list[str] | None = None,
) -> EnrichedTerm:
    hr = HarvestRecord(
        text="x",
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="ui"),
        tier=Tier.UNSTRUCTURED,
    )
    t = EnrichedTerm.from_harvest(hr)
    t.candidate_labels = [CandidateLabel(text=label, confidence=0.9)]
    if target_uri is not None:
        t.match_result = MatchResult(MatchType.DUPLICATE, 1.0, target_uri)
    t.definition = definition
    if policy_paragraphs:
        t.policy_context = [
            PolicyContext(paragraph=p, document_ref="CreditPolicy_v3.pdf")
            for p in policy_paragraphs
        ]
    return t


# ---------- the user's headline test case ----------

def test_holds_relation_resolves_to_bank_rel_holds_held_by(base_ontology):
    """The proposal's example: definition mentions 'holds' → resolved relation
    using bank-rel:holds + bank-rel:heldBy."""
    agent = RelationsAgent(base_ontology)
    term = _term(
        definition="A retail customer who holds instalment-based credit products"
    )
    relations = agent.evaluate(term)
    assert len(relations) == 1
    rel = relations[0]
    assert rel.status is RelationStatus.RESOLVED
    assert rel.subject_uri == RETAIL_CUSTOMER_URI
    assert rel.predicate_uri == f"{REL_NS}holds"
    assert rel.inverse_predicate_uri == f"{REL_NS}heldBy"
    assert rel.verb == "holds"
    assert "credit products" in rel.object_label


# ---------- multiple lexicon verbs ----------

def test_extracts_multiple_resolved_relations(base_ontology):
    agent = RelationsAgent(base_ontology)
    term = _term(
        definition=(
            "A customer holds a PI loan and uses the mobile app and submits "
            "loan applications."
        )
    )
    relations = agent.evaluate(term)
    verbs = [r.verb for r in relations]
    assert verbs == ["holds", "uses", "submits"]
    assert all(r.status is RelationStatus.RESOLVED for r in relations)
    predicates = {r.predicate_uri for r in relations}
    assert predicates == {f"{REL_NS}holds", f"{REL_NS}uses", f"{REL_NS}submits"}


def test_resolves_triggers_and_requires(base_ontology):
    agent = RelationsAgent(base_ontology)
    term = _term(
        label="Loan application",
        definition="Loan application triggers credit check and requires KYC.",
        target_uri="http://ontobridge.dev/ontology/bank/LoanApplication",
    )
    rels = agent.evaluate(term)
    assert {r.verb for r in rels} == {"triggers", "requires"}
    for r in rels:
        assert r.status is RelationStatus.RESOLVED


# ---------- unresolved verb flagging ----------

def test_unknown_verb_flagged_as_unresolved_not_dropped(base_ontology):
    agent = RelationsAgent(base_ontology)
    term = _term(
        label="Mobile app",
        definition="Mobile app processes customer transactions.",
        target_uri="http://ontobridge.dev/ontology/bank/MobileApp",
    )
    rels = agent.evaluate(term)
    assert len(rels) == 1
    rel = rels[0]
    assert rel.status is RelationStatus.UNRESOLVED_VERB
    assert rel.verb == "processes"
    assert rel.predicate_uri is None
    assert rel.inverse_predicate_uri is None
    assert rel.confidence < 1.0  # unresolved relations carry reduced confidence
    # The object label is still preserved so the steward can review.
    assert "transactions" in rel.object_label


def test_mixed_resolved_and_unresolved_in_same_definition(base_ontology):
    agent = RelationsAgent(base_ontology)
    term = _term(
        definition="Customer holds a credit product and manages the account."
    )
    rels = agent.evaluate(term)
    by_verb = {r.verb: r for r in rels}
    assert by_verb["holds"].status is RelationStatus.RESOLVED
    # "manages" is a recognised SVO verb but has no ontology relation pair.
    assert by_verb["manages"].status is RelationStatus.UNRESOLVED_VERB


# ---------- subject anchoring ----------

def test_subject_uri_uses_match_result_target_when_available(base_ontology):
    agent = RelationsAgent(base_ontology)
    term = _term(definition="Customer holds a product")
    rels = agent.evaluate(term)
    assert rels[0].subject_uri == RETAIL_CUSTOMER_URI


def test_subject_uri_falls_back_to_taxonomy_curie(base_ontology):
    from ontobridge.models import PlacementStatus, TaxonomyPlacement

    agent = RelationsAgent(base_ontology)
    term = _term(definition="Customer holds a product", target_uri=None)
    term.taxonomy_placement = TaxonomyPlacement(
        broader_concept_uri="bank:Customer",
        scheme_uri="bank:SchemeParty",
        domain_prefix="bank:RetailCustomer",
        status=PlacementStatus.PLACED,
    )
    rels = agent.evaluate(term)
    assert rels[0].subject_uri == "bank:RetailCustomer"


def test_subject_uri_falls_back_to_synthetic_when_unmapped(base_ontology):
    agent = RelationsAgent(base_ontology)
    term = _term(definition="Customer holds a product", target_uri=None)
    rels = agent.evaluate(term)
    assert rels[0].subject_uri.startswith("_:candidate/")


def test_evaluate_raises_when_term_has_no_anchor(base_ontology):
    hr = HarvestRecord(
        text="x",
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="ui"),
        tier=Tier.UNSTRUCTURED,
    )
    bare = EnrichedTerm.from_harvest(hr)
    bare.definition = "Customer holds a product"
    with pytest.raises(ValueError, match="subject"):
        RelationsAgent(base_ontology).evaluate(bare)


# ---------- text sources ----------

def test_policy_context_paragraphs_are_scanned(base_ontology):
    agent = RelationsAgent(base_ontology)
    term = _term(
        definition=None,
        policy_paragraphs=["The retail customer holds a credit product."],
    )
    rels = agent.evaluate(term)
    assert len(rels) == 1 and rels[0].verb == "holds"


def test_definition_and_policy_context_combined(base_ontology):
    agent = RelationsAgent(base_ontology)
    term = _term(
        definition="Customer holds a loan.",
        policy_paragraphs=["The application triggers a credit check."],
    )
    verbs = sorted(r.verb for r in agent.evaluate(term))
    assert verbs == ["holds", "triggers"]


def test_no_text_yields_empty_relations(base_ontology):
    agent = RelationsAgent(base_ontology)
    term = _term(definition=None)
    assert agent.evaluate(term) == []


# ---------- agent contract ----------

def test_apply_writes_relations_into_term(base_ontology):
    agent = RelationsAgent(base_ontology)
    term = _term(definition="Customer holds a product")
    returned = agent.apply(term)
    assert returned is term
    assert len(term.relations) == 1
    assert term.relations[0].status is RelationStatus.RESOLVED


# ---------- pluggable extractor ----------

def test_custom_extractor_protocol_can_replace_default(base_ontology):
    """Demonstrates the SVOExtractor protocol — an alternate extractor (e.g.
    spaCy in production) plugs in without touching the agent."""

    class StubExtractor(SVOExtractor):
        def extract(self, text, *, default_subject=None):
            return [
                SVOTriple(subject=default_subject or "X", verb="governs", object="loan policy"),
            ]

    agent = RelationsAgent(base_ontology, extractor=StubExtractor())
    term = _term(definition="ignored text")
    rels = agent.evaluate(term)
    assert len(rels) == 1
    assert rels[0].verb == "governs"
    assert rels[0].predicate_uri == f"{REL_NS}governs"


def test_custom_lexicon_can_replace_default(base_ontology):
    custom = InverseVerbLexicon([])
    agent = RelationsAgent(base_ontology, lexicon=custom)
    term = _term(definition="Customer holds a product")
    rels = agent.evaluate(term)
    # Empty lexicon → every recognised verb becomes unresolved.
    assert len(rels) == 1
    assert rels[0].status is RelationStatus.UNRESOLVED_VERB
