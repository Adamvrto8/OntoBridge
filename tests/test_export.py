from __future__ import annotations

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from ontobridge.export import export_all_statuses, export_turtle
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_runner(base_ontology) -> tuple[PipelineRunner, InMemoryPublisher]:
    pub = InMemoryPublisher()
    runner = PipelineRunner(base_ontology, pub)
    return runner, pub


def _run_term(
    runner: PipelineRunner,
    label: str,
    definition: str,
    section: str = "1.1",
    approved_by: str | None = None,
) -> None:
    harvest = HarvestRecord(
        text=definition,
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="Policy.pdf", section=section),
        tier=Tier.DOCUMENT,
    )
    term = EnrichedTerm.from_harvest(harvest)
    term.candidate_labels = [CandidateLabel(text=label, confidence=0.95)]
    term.definition = definition
    term.policy_context = [
        PolicyContext(paragraph=definition, document_ref="Policy.pdf", section=section)
    ]
    runner.run(term, approved_by=approved_by)


# ---------------------------------------------------------------------------
# Basic output
# ---------------------------------------------------------------------------

def test_export_returns_string(base_ontology):
    _, pub = _make_runner(base_ontology)
    ttl = export_turtle(pub)
    assert isinstance(ttl, str)


def test_export_empty_publisher_returns_valid_turtle(base_ontology):
    _, pub = _make_runner(base_ontology)
    ttl = export_turtle(pub)
    g = Graph()
    g.parse(data=ttl, format="turtle")
    assert len(g) > 0  # at least the ontology header triples


def test_export_includes_ontology_header(base_ontology):
    _, pub = _make_runner(base_ontology)
    ttl = export_turtle(pub)
    g = Graph()
    g.parse(data=ttl, format="turtle")
    ontology_nodes = list(g.subjects(RDF.type, OWL.Ontology))
    assert len(ontology_nodes) == 1


def test_export_header_contains_title(base_ontology):
    _, pub = _make_runner(base_ontology)
    ttl = export_turtle(pub, title="My Custom Glossary")
    assert "My Custom Glossary" in ttl


def test_export_is_valid_turtle(base_ontology):
    runner, pub = _make_runner(base_ontology)
    _run_term(
        runner, "Premium retail customer",
        "A retail customer who holds premium credit products with the bank "
        "and uses concierge channels for high-touch service.",
        approved_by="alice",
    )
    ttl = export_turtle(pub)
    g = Graph()
    g.parse(data=ttl, format="turtle")
    assert len(g) > 0


# ---------------------------------------------------------------------------
# Status filtering
# ---------------------------------------------------------------------------

def test_default_export_includes_only_published(base_ontology):
    runner, pub = _make_runner(base_ontology)
    # Approved → PUBLISHED
    _run_term(
        runner, "Premium retail customer",
        "A retail customer who holds premium credit products with the bank "
        "and uses concierge channels for high-touch service.",
        approved_by="alice",
    )
    # No approver → REVIEW (not included by default)
    _run_term(
        runner, "Loan Repayment Schedule",
        "A document that governs the periodic repayment instalments a customer "
        "submits against an outstanding loan obligation.",
    )

    published_ttl = export_turtle(pub)
    g = Graph()
    g.parse(data=published_ttl, format="turtle")
    labels = [str(o) for _, _, o in g.triples((None, SKOS.prefLabel, None))]
    assert any("Premium retail customer" in lbl for lbl in labels)
    assert not any("Loan Repayment Schedule" in lbl for lbl in labels)


def test_custom_status_set_includes_review(base_ontology):
    runner, pub = _make_runner(base_ontology)
    _run_term(
        runner, "Loan Repayment Schedule",
        "A document that governs the periodic repayment instalments a customer "
        "submits against an outstanding loan obligation.",
    )
    ttl = export_turtle(pub, statuses={LifecycleStatus.REVIEW})
    g = Graph()
    g.parse(data=ttl, format="turtle")
    labels = [str(o) for _, _, o in g.triples((None, SKOS.prefLabel, None))]
    assert any("Loan Repayment Schedule" in lbl for lbl in labels)


def test_export_all_statuses_includes_every_term(base_ontology):
    runner, pub = _make_runner(base_ontology)
    _run_term(
        runner, "Premium retail customer",
        "A retail customer who holds premium credit products with the bank "
        "and uses concierge channels for high-touch service.",
        approved_by="alice",
    )
    _run_term(
        runner, "Loan Repayment Schedule",
        "A document that governs the periodic repayment instalments a customer "
        "submits against an outstanding loan obligation.",
    )
    # Duplicate label → CANDIDATE
    _run_term(
        runner, "Retail customer",
        "A natural person who holds retail products at the bank for personal use.",
    )

    ttl = export_all_statuses(pub)
    g = Graph()
    g.parse(data=ttl, format="turtle")
    labels = {str(o) for _, _, o in g.triples((None, SKOS.prefLabel, None))}
    assert len(labels) >= 2


# ---------------------------------------------------------------------------
# Turtle content correctness
# ---------------------------------------------------------------------------

def test_exported_graph_contains_pref_label(base_ontology):
    runner, pub = _make_runner(base_ontology)
    _run_term(
        runner, "Premium retail customer",
        "A retail customer who holds premium credit products with the bank "
        "and uses concierge channels for high-touch service.",
        approved_by="alice",
    )
    ttl = export_turtle(pub)
    g = Graph()
    g.parse(data=ttl, format="turtle")
    labels = [str(o) for _, _, o in g.triples((None, SKOS.prefLabel, None))]
    assert any("Premium retail customer" in lbl for lbl in labels)


def test_exported_graph_contains_broader(base_ontology):
    runner, pub = _make_runner(base_ontology)
    _run_term(
        runner, "Premium retail customer",
        "A retail customer who holds premium credit products with the bank "
        "and uses concierge channels for high-touch service.",
        approved_by="alice",
    )
    ttl = export_turtle(pub)
    g = Graph()
    g.parse(data=ttl, format="turtle")
    assert any(True for _ in g.triples((None, SKOS.broader, None)))


def test_multiple_terms_merged_into_one_graph(base_ontology):
    runner, pub = _make_runner(base_ontology)
    _run_term(
        runner, "Premium retail customer",
        "A retail customer who holds premium credit products with the bank "
        "and uses concierge channels for high-touch service.",
        approved_by="alice",
    )
    _run_term(
        runner, "Voluntary early settlement",
        "A formal request submitted by a borrower to fully repay an outstanding "
        "credit balance before the contractual maturity date, typically incurring "
        "an early settlement charge.",
        approved_by="bob",
    )
    ttl = export_turtle(pub)
    g = Graph()
    g.parse(data=ttl, format="turtle")
    labels = {str(o) for _, _, o in g.triples((None, SKOS.prefLabel, None))}
    assert len(labels) == 2


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------

def test_export_writes_to_file(base_ontology, tmp_path):
    _, pub = _make_runner(base_ontology)
    out = tmp_path / "glossary.ttl"
    export_turtle(pub, output_path=out)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "@prefix" in content


def test_export_creates_parent_dirs(base_ontology, tmp_path):
    _, pub = _make_runner(base_ontology)
    out = tmp_path / "exports" / "sub" / "glossary.ttl"
    export_turtle(pub, output_path=out)
    assert out.exists()


def test_export_returns_same_string_as_file(base_ontology, tmp_path):
    _, pub = _make_runner(base_ontology)
    out = tmp_path / "glossary.ttl"
    returned = export_turtle(pub, output_path=out)
    written = out.read_text(encoding="utf-8")
    assert returned == written


# ---------------------------------------------------------------------------
# Robustness — terms with no turtle are skipped silently
# ---------------------------------------------------------------------------

def test_terms_without_turtle_are_skipped(base_ontology):
    from ontobridge.models.published import PublishedTerm

    pub = InMemoryPublisher()

    harvest = HarvestRecord(
        text="Some definition text for a term without turtle.",
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="P.pdf"),
        tier=Tier.DOCUMENT,
    )
    enriched = EnrichedTerm.from_harvest(harvest)
    enriched.candidate_labels = [CandidateLabel(text="No Turtle Term", confidence=0.9)]
    enriched.definition = harvest.text

    pub.create_term(PublishedTerm(
        enriched_term=enriched,
        term_uri="bank:NoTurtleTerm",
        lifecycle_status=LifecycleStatus.PUBLISHED,
        approved_by="alice",
        turtle=None,
    ))

    ttl = export_turtle(pub)
    g = Graph()
    g.parse(data=ttl, format="turtle")
    # Export succeeds, ontology header present, term not in graph
    assert any(True for _ in g.subjects(RDF.type, OWL.Ontology))
    labels = [str(o) for _, _, o in g.triples((None, SKOS.prefLabel, None))]
    assert not any("No Turtle" in lbl for lbl in labels)
