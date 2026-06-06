"""Tests for steady-state ingestion: PipelineRunner.ingest() upsert + drift.

When a document re-mentions a term that is already published, the term must
NOT be duplicated. Instead the new document is folded in as provenance (and any
new synonyms), and — when the document defines the term differently — the term
is flagged for steward review (drift) rather than silently overwritten.
"""
from __future__ import annotations

import pytest

from ontobridge.models import (
    CandidateLabel,
    EnrichedTerm,
    HarvestRecord,
    PolicyContext,
    SourceRef,
    SourceType,
    Tier,
)
from ontobridge.models.enums import LifecycleStatus
from ontobridge.pipeline import PipelineRunner, RunResult
from ontobridge.pipeline_config import PipelineConfig
from ontobridge.publisher import InMemoryPublisher


def _term(
    label: str,
    definition: str,
    *,
    document_ref: str = "DocA.pdf",
    section: str = "1.0",
    extra_labels: list[tuple[str, float]] | None = None,
) -> EnrichedTerm:
    record = HarvestRecord(
        text=definition,
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id=document_ref),
        tier=Tier.DOCUMENT,
    )
    t = EnrichedTerm.from_harvest(record)
    t.candidate_labels = [CandidateLabel(text=label, confidence=0.95)]
    for text, conf in (extra_labels or []):
        t.candidate_labels.append(CandidateLabel(text=text, confidence=conf))
    t.definition = definition
    t.policy_context = [
        PolicyContext(paragraph=definition, document_ref=document_ref, section=section)
    ]
    return t


def _runner(ontology, publisher) -> PipelineRunner:
    return PipelineRunner(ontology=ontology, publisher=publisher)


_DEF = "The percentage of loans in a portfolio that are past due by more than ninety days."
_DEF_DRIFT = (
    "A monthly indicator computed by the risk team to track borrower repayment "
    "behaviour and arrears across customer segments and products."
)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def test_new_term_is_created(base_ontology):
    pub = InMemoryPublisher()
    runner = _runner(base_ontology, pub)
    result = runner.ingest(_term("Delinquency Rate", _DEF))
    assert isinstance(result, RunResult)
    assert result.action == "created"
    assert len(pub.search_terms("")) == 1


# ---------------------------------------------------------------------------
# Merge (no drift)
# ---------------------------------------------------------------------------

def test_reingesting_same_term_merges(base_ontology):
    pub = InMemoryPublisher()
    runner = _runner(base_ontology, pub)
    runner.ingest(_term("Delinquency Rate", _DEF))
    result = runner.ingest(_term("Delinquency Rate", _DEF))

    assert result.action == "merged"
    assert len(pub.search_terms("")) == 1            # no duplicate
    assert result.term.version == 2                   # update_term bumped version


def test_merge_appends_provenance_from_new_document(base_ontology):
    pub = InMemoryPublisher()
    runner = _runner(base_ontology, pub)
    created = runner.ingest(_term("Delinquency Rate", _DEF, document_ref="DocA.pdf"))
    uri = created.term.term_uri

    runner.ingest(_term("Delinquency Rate", _DEF, document_ref="DocB.pdf", section="2.0"))

    refs = {p.document_ref for p in pub.get_term(uri).enriched_term.policy_context}
    assert refs == {"DocA.pdf", "DocB.pdf"}


def test_merge_does_not_overwrite_definition(base_ontology):
    pub = InMemoryPublisher()
    runner = _runner(base_ontology, pub)
    created = runner.ingest(_term("Delinquency Rate", _DEF))
    uri = created.term.term_uri

    # Same concept, same-enough wording — should merge, original definition kept.
    runner.ingest(_term("Delinquency Rate", _DEF))
    assert pub.get_term(uri).enriched_term.definition == _DEF


def test_merge_folds_in_new_synonyms(base_ontology):
    pub = InMemoryPublisher()
    runner = _runner(base_ontology, pub)
    created = runner.ingest(_term("Delinquency Rate", _DEF))
    uri = created.term.term_uri

    runner.ingest(
        _term("Delinquency Rate", _DEF, extra_labels=[("DQ Rate", 0.7)])
    )
    labels = {c.text.casefold() for c in pub.get_term(uri).enriched_term.candidate_labels}
    assert "dq rate" in labels


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------

def test_divergent_definition_flags_drift(base_ontology):
    pub = InMemoryPublisher()
    runner = _runner(base_ontology, pub)
    created = runner.ingest(_term("Delinquency Rate", _DEF))
    uri = created.term.term_uri

    result = runner.ingest(_term("Delinquency Rate", _DEF_DRIFT, document_ref="DocB.pdf"))

    assert result.action == "drifted"
    assert pub.get_term(uri).lifecycle_status is LifecycleStatus.REVIEW
    # Published definition is preserved — steward decides, not the pipeline.
    assert pub.get_term(uri).enriched_term.definition == _DEF
    # The diverging source was still recorded as provenance for comparison.
    refs = {p.document_ref for p in pub.get_term(uri).enriched_term.policy_context}
    assert "DocB.pdf" in refs


def test_identical_definition_is_not_drift(base_ontology):
    pub = InMemoryPublisher()
    runner = _runner(base_ontology, pub)
    runner.ingest(_term("Delinquency Rate", _DEF))
    result = runner.ingest(_term("Delinquency Rate", _DEF, document_ref="DocB.pdf"))
    assert result.action == "merged"


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["merge_threshold", "drift_threshold"])
def test_threshold_out_of_range_rejected(field):
    with pytest.raises(ValueError):
        PipelineConfig(**{field: 1.5})


# ---------------------------------------------------------------------------
# Batch-level reporting
# ---------------------------------------------------------------------------

def test_batch_reports_merged_and_drifted(base_ontology):
    from ontobridge.batch import BatchPipelineRunner

    pub = InMemoryPublisher()
    batch = BatchPipelineRunner(ontology=base_ontology, publisher=pub)

    # Week 1: establish the term.
    batch.run_terms([_term("Delinquency Rate", _DEF)])

    # Week 2: one identical re-mention (merge) + one divergent re-mention (drift).
    result = batch.run_terms([
        _term("Delinquency Rate", _DEF, document_ref="DocB.pdf"),
        _term("Delinquency Rate", _DEF_DRIFT, document_ref="DocC.pdf"),
    ])
    # Both within-batch re-mentions resolve against the published term.
    assert len(result.merged) + len(result.drifted) == 2
    assert len(result.drifted) >= 1
    assert len(result.published) == 0
    assert len(pub.search_terms("")) == 1
