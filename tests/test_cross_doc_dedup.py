"""Tests for cross-document (and within-document) deduplication.

The MappingAgent now checks incoming terms against BOTH the static
ontology concepts AND all already-published terms in the publisher.
This means near-duplicate labels submitted across different documents
are flagged by governance instead of silently creating duplicates.
"""
from __future__ import annotations

import pytest

from ontobridge.agents.mapping.glossary import (
    CombinedGlossarySource,
    PublisherGlossarySource,
    from_ontology,
)
from ontobridge.models import (
    CandidateLabel,
    EnrichedTerm,
    HarvestRecord,
    PolicyContext,
    SourceRef,
    SourceType,
    Tier,
)
from ontobridge.models.enums import LifecycleStatus, MatchType
from ontobridge.pipeline import PipelineRunner
from ontobridge.publisher import InMemoryPublisher


def _term(label: str, definition: str) -> EnrichedTerm:
    record = HarvestRecord(
        text=definition,
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="test.pdf"),
        tier=Tier.DOCUMENT,
    )
    t = EnrichedTerm.from_harvest(record)
    t.candidate_labels = [CandidateLabel(text=label, confidence=0.9)]
    t.definition = definition
    t.policy_context = [
        PolicyContext(
            paragraph=definition,
            document_ref="test.pdf",
            section="1.0",
        )
    ]
    return t


def _make_runner(ontology, publisher) -> PipelineRunner:
    return PipelineRunner(ontology=ontology, publisher=publisher)


# ---------------------------------------------------------------------------
# PublisherGlossarySource
# ---------------------------------------------------------------------------

def test_publisher_glossary_is_empty_initially(base_ontology):
    pub = InMemoryPublisher()
    src = PublisherGlossarySource(pub)
    assert list(src.entries()) == []


def test_publisher_glossary_reflects_published_terms(base_ontology):
    pub = InMemoryPublisher()
    runner = _make_runner(base_ontology, pub)
    term = _term(
        "Delinquency Rate",
        "The percentage of loans that are past due by more than 90 days in a portfolio.",
    )
    runner.run(term)

    src = PublisherGlossarySource(pub)
    labels = [e.pref_label.lower() for e in src.entries()]
    assert any("delinquency" in l for l in labels)


# ---------------------------------------------------------------------------
# CombinedGlossarySource
# ---------------------------------------------------------------------------

def test_combined_glossary_yields_from_all_sources(base_ontology):
    pub = InMemoryPublisher()
    combined = CombinedGlossarySource(from_ontology(base_ontology), PublisherGlossarySource(pub))
    entries = list(combined.entries())
    # Should contain at least the ontology concepts
    assert len(entries) >= len(list(from_ontology(base_ontology).entries()))


# ---------------------------------------------------------------------------
# Cross-document deduplication via MappingAgent
# ---------------------------------------------------------------------------

def test_exact_duplicate_label_flagged_after_first_publish(base_ontology):
    """Second submission with the same label gets DUPLICATE match_type."""
    pub = InMemoryPublisher()
    runner = _make_runner(base_ontology, pub)

    first = _term(
        "Non-Performing Loan",
        "A loan where the borrower has not made scheduled payments for at least 90 days.",
    )
    runner.run(first)

    second = _term(
        "Non-Performing Loan",
        "A credit facility classified as non-performing when overdue by 90 or more days.",
    )
    second.match_result = runner.mapping.evaluate(second)
    assert second.match_result.match_type == MatchType.DUPLICATE


def test_fuzzy_duplicate_label_flagged_after_first_publish(base_ontology):
    """Near-duplicate label from a different document gets FUZZY match_type."""
    pub = InMemoryPublisher()
    runner = _make_runner(base_ontology, pub)

    first = _term(
        "Loan Default",
        "A borrower's failure to meet the repayment obligations of a loan agreement.",
    )
    runner.run(first)

    # Different word order, same concept
    second = _term(
        "Default on Loan",
        "The event in which a borrower fails to repay a loan as contractually required.",
    )
    second.match_result = runner.mapping.evaluate(second)
    # Should be FUZZY, not NEW
    assert second.match_result.match_type in (MatchType.FUZZY, MatchType.DUPLICATE)


def test_unrelated_term_not_flagged(base_ontology):
    """A genuinely different term still gets NEW match_type."""
    pub = InMemoryPublisher()
    runner = _make_runner(base_ontology, pub)

    first = _term(
        "Loan Default",
        "A borrower's failure to meet the repayment obligations of a loan agreement.",
    )
    runner.run(first)

    second = _term(
        "Butterfly Option Strategy",
        "An options strategy combining bull and bear spreads with a fixed risk and capped profit.",
    )
    second.match_result = runner.mapping.evaluate(second)
    assert second.match_result.match_type == MatchType.NEW


# ---------------------------------------------------------------------------
# Within-document (within-batch) deduplication
# ---------------------------------------------------------------------------

def test_within_batch_duplicate_caught(base_ontology):
    """Term published earlier in the same batch blocks an identical second term."""
    from ontobridge.batch import BatchPipelineRunner

    pub = InMemoryPublisher()
    batch = BatchPipelineRunner(ontology=base_ontology, publisher=pub)

    t1 = _term(
        "Credit Default Swap",
        "A financial derivative that transfers credit risk of a reference entity between parties.",
    )
    t2 = _term(
        "Credit Default Swap",
        "A derivative instrument used to hedge or speculate on the credit risk of an entity.",
    )

    result = batch.run_terms([t1, t2])

    # t1 published once; t2 is recognised as the same term and merged in as
    # additional provenance rather than creating a duplicate.
    published_labels = [p.enriched_term.preferred_label for p in result.published]
    assert published_labels.count("Credit Default Swap") == 1
    assert len(result.merged) + len(result.drifted) == 1
    total_seen = (
        len(result.published) + len(result.merged) + len(result.drifted)
        + len(result.skipped) + len(result.failed)
    )
    assert total_seen == 2


def test_publisher_glossary_updates_between_terms(base_ontology):
    """After publishing term A, the publisher glossary immediately includes A."""
    pub = InMemoryPublisher()
    runner = _make_runner(base_ontology, pub)

    t_a = _term(
        "Prepayment Penalty",
        "A fee charged to a borrower who repays a loan before the scheduled maturity date.",
    )
    runner.run(t_a)

    # Publisher now contains "Prepayment Penalty"
    src = PublisherGlossarySource(pub)
    labels = [e.pref_label.lower() for e in src.entries()]
    assert any("prepayment" in l for l in labels)
