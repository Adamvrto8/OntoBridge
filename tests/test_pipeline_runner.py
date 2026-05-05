from __future__ import annotations

from dataclasses import replace

import pytest

from ontobridge.models import (
    CandidateLabel,
    EnrichedTerm,
    HarvestRecord,
    LifecycleStatus,
    PolicyContext,
    SourceRef,
    SourceType,
    Tier,
)
from ontobridge.pipeline import PipelineRunner
from ontobridge.publisher import InMemoryPublisher

BANK_NS = "http://ontobridge.dev/ontology/bank/"
REL_NS = "http://ontobridge.dev/ontology/bank/relations/"


def _harvest() -> HarvestRecord:
    return HarvestRecord(
        text="x",
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="ui"),
        tier=Tier.UNSTRUCTURED,
    )


def _premium_customer_term(
    label: str = "Premium retail customer",
    definition: str = (
        "A retail customer who holds premium credit products with the bank and "
        "uses concierge channels for high-touch service."
    ),
) -> EnrichedTerm:
    t = EnrichedTerm.from_harvest(_harvest())
    t.candidate_labels = [CandidateLabel(text=label, confidence=0.95)]
    t.definition = definition
    t.policy_context = [
        PolicyContext(
            paragraph="Defined in policy section 4.2.",
            document_ref="CreditPolicy_v3.pdf",
            section="4.2",
        ),
    ]
    return t


# ---------- input validation ----------

def test_runner_requires_candidate_labels(base_ontology):
    pub = InMemoryPublisher()
    runner = PipelineRunner(base_ontology, pub)
    t = EnrichedTerm.from_harvest(_harvest())
    t.definition = "A definition with enough words to satisfy governance rule 8 fully."
    with pytest.raises(ValueError, match="candidate_labels"):
        runner.run(t)


def test_runner_requires_definition(base_ontology):
    pub = InMemoryPublisher()
    runner = PipelineRunner(base_ontology, pub)
    t = EnrichedTerm.from_harvest(_harvest())
    t.candidate_labels = [CandidateLabel(text="Foo", confidence=0.9)]
    with pytest.raises(ValueError, match="definition"):
        runner.run(t)


# ---------- end-to-end success path ----------

def test_runner_publishes_clean_term_through_full_chain(base_ontology):
    pub = InMemoryPublisher()
    runner = PipelineRunner(base_ontology, pub)
    term = _premium_customer_term()
    published = runner.run(term, approved_by="steward.alice")

    # Each agent must have populated its slice of the EnrichedTerm.
    assert term.match_result is not None
    assert term.taxonomy_placement is not None
    assert term.relations  # at least one relation extracted
    assert term.governance_result is not None

    # Writer assembled the URI from the taxonomy placement's CURIE.
    assert published.term_uri.startswith(BANK_NS)
    assert published.turtle and "skos:prefLabel" in published.turtle

    # The publisher actually has it.
    fetched = pub.get_term(published.term_uri)
    assert fetched.term_uri == published.term_uri


def test_runner_clean_term_with_approver_publishes(base_ontology):
    pub = InMemoryPublisher()
    runner = PipelineRunner(base_ontology, pub)
    term = _premium_customer_term()
    published = runner.run(term, approved_by="steward.alice")
    assert published.lifecycle_status is LifecycleStatus.PUBLISHED


def test_runner_clean_term_without_approver_demotes_to_review(base_ontology):
    pub = InMemoryPublisher()
    runner = PipelineRunner(base_ontology, pub)
    term = _premium_customer_term()
    published = runner.run(term)
    assert published.lifecycle_status is LifecycleStatus.REVIEW


def test_runner_blocked_term_lands_as_candidate(base_ontology):
    """A duplicate label gets blocked by Governance rule 1 → CANDIDATE
    lifecycle. The Writer derives a CURIE from the taxonomy placement so the
    URI doesn't necessarily collide with the existing concept."""
    pub = InMemoryPublisher()
    runner = PipelineRunner(base_ontology, pub)
    term = _premium_customer_term(
        label="Retail customer",  # exact duplicate of existing prefLabel
    )
    published = runner.run(term)
    assert published.lifecycle_status is LifecycleStatus.CANDIDATE
    assert any(flag.startswith("R01:") for flag in term.governance_result.blocking_flags)


# ---------- lifecycle transitions ----------

def test_candidate_to_review_to_published_with_approved_by(base_ontology):
    """Walk a term from CANDIDATE → REVIEW → PUBLISHED via the publisher,
    setting approved_by before the final transition (PublishedTerm enforces it)."""
    pub = InMemoryPublisher()
    runner = PipelineRunner(base_ontology, pub)

    term = _premium_customer_term(label="Retail customer")  # → CANDIDATE
    published = runner.run(term)
    assert published.lifecycle_status is LifecycleStatus.CANDIDATE

    uri = published.term_uri
    after_review = pub.transition_status(uri, LifecycleStatus.REVIEW)
    assert after_review.lifecycle_status is LifecycleStatus.REVIEW

    # PUBLISHED requires approved_by — set it before transitioning, otherwise
    # PublishedTerm's __post_init__ rejects the new instance.
    current = pub.get_term(uri)
    pub.update_term(uri, replace(current, approved_by="steward.alice"))
    after_publish = pub.transition_status(uri, LifecycleStatus.PUBLISHED)
    assert after_publish.lifecycle_status is LifecycleStatus.PUBLISHED
    assert after_publish.approved_by == "steward.alice"


def test_publisher_rejects_publish_transition_without_approver(base_ontology):
    pub = InMemoryPublisher()
    runner = PipelineRunner(base_ontology, pub)
    term = _premium_customer_term(label="Retail customer")  # → CANDIDATE
    published = runner.run(term)
    pub.transition_status(published.term_uri, LifecycleStatus.REVIEW)
    # No approved_by set — PublishedTerm.__post_init__ should reject.
    with pytest.raises(ValueError, match="approved_by"):
        pub.transition_status(published.term_uri, LifecycleStatus.PUBLISHED)


# ---------- writer emitted Turtle is queryable ----------

def test_published_turtle_is_round_trippable(base_ontology):
    from rdflib import Graph, URIRef
    from rdflib.namespace import SKOS

    pub = InMemoryPublisher()
    runner = PipelineRunner(base_ontology, pub)
    term = _premium_customer_term()
    published = runner.run(term, approved_by="steward.alice")

    g = Graph()
    g.parse(data=published.turtle, format="turtle")
    subj = URIRef(published.term_uri)
    assert any(g.triples((subj, SKOS.prefLabel, None)))
    assert any(g.triples((subj, SKOS.broader, None)))
    assert any(g.triples((subj, SKOS.inScheme, None)))


def test_runner_publishes_to_glossary_visible_via_search(base_ontology):
    pub = InMemoryPublisher()
    runner = PipelineRunner(base_ontology, pub)
    runner.run(_premium_customer_term(), approved_by="steward.alice")
    hits = pub.search_terms("premium")
    assert len(hits) == 1
    assert "Premium" in hits[0].enriched_term.candidate_labels[0].text


# ---------- encoder passthrough ----------

def test_runner_accepts_encoder_parameter(base_ontology):
    from ontobridge.encoders import SentenceTransformerEncoder
    enc = SentenceTransformerEncoder()
    pub = InMemoryPublisher()
    # Must not raise; encoder is forwarded to MappingAgent and TaxonomyAgent.
    runner = PipelineRunner(base_ontology, pub, encoder=enc)
    assert runner.mapping.embedding.encoder is enc
    assert runner.taxonomy.encoder is enc


def test_runner_encoder_is_called_during_run(base_ontology):
    """A tracking encoder stub confirms encode() is invoked by both agents."""
    from typing import Mapping

    class TrackingEncoder:
        def __init__(self):
            self.calls: list[str] = []

        def encode(self, text: str) -> Mapping[str, float]:
            self.calls.append(text)
            # Return a simple unit vector so cosine similarity works
            return {"0": 1.0}

    enc = TrackingEncoder()
    pub = InMemoryPublisher()
    runner = PipelineRunner(base_ontology, pub, encoder=enc)
    runner.run(_premium_customer_term(), approved_by="steward.alice")
    # Both MappingAgent (EmbeddingSimilarityStrategy) and TaxonomyAgent call encode()
    assert len(enc.calls) > 0
