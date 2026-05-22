"""Tests for FIBO definition fallback in PipelineRunner."""
from __future__ import annotations

from dataclasses import replace

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
from ontobridge.models.fibo import FIBOMatch
from ontobridge.pipeline import PipelineRunner
from ontobridge.publisher import InMemoryPublisher


_FIBO_DEF = (
    "Credit risk is the risk of loss arising from a borrower's failure to "
    "repay a loan or meet contractual obligations."
)
_DOC_DEF = (
    "Credit risk means the chance that a customer will not pay back the money "
    "they borrowed from the bank."
)


def _make_term(definition: str | None, fibo_definition: str | None = None) -> EnrichedTerm:
    record = HarvestRecord(
        text=definition or "x",
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="doc.pdf"),
        tier=Tier.DOCUMENT,
    )
    t = EnrichedTerm.from_harvest(record)
    t.candidate_labels = [CandidateLabel(text="Credit Risk", confidence=0.9)]
    t.definition = definition
    t.policy_context = [PolicyContext(paragraph="x", document_ref="doc.pdf", section="1")]
    if fibo_definition:
        t.fibo_match = FIBOMatch(
            uri="https://spec.edmcouncil.org/fibo/CreditRisk",
            match_type="exact",
            expected_definition=fibo_definition,
        )
    return t


# ---------------------------------------------------------------------------
# _fibo_definition_fallback()
# ---------------------------------------------------------------------------

def test_fibo_definition_used_when_definition_missing(base_ontology):
    pub = InMemoryPublisher()
    runner = PipelineRunner(ontology=base_ontology, publisher=pub)
    term = _make_term(definition=None, fibo_definition=_FIBO_DEF)

    PipelineRunner._fibo_definition_fallback(term)

    assert term.definition == _FIBO_DEF
    assert term.definition_source == "fibo"


def test_fibo_definition_used_when_definition_too_short(base_ontology):
    pub = InMemoryPublisher()
    runner = PipelineRunner(ontology=base_ontology, publisher=pub)
    term = _make_term(definition="Short text.", fibo_definition=_FIBO_DEF)

    PipelineRunner._fibo_definition_fallback(term)

    assert term.definition == _FIBO_DEF
    assert term.definition_source == "fibo"


def test_good_definition_not_overridden_by_fibo(base_ontology):
    pub = InMemoryPublisher()
    runner = PipelineRunner(ontology=base_ontology, publisher=pub)
    term = _make_term(definition=_DOC_DEF, fibo_definition=_FIBO_DEF)

    PipelineRunner._fibo_definition_fallback(term)

    assert term.definition == _DOC_DEF
    assert term.definition_source == "document"


def test_no_fibo_match_leaves_definition_unchanged(base_ontology):
    pub = InMemoryPublisher()
    runner = PipelineRunner(ontology=base_ontology, publisher=pub)
    term = _make_term(definition=None, fibo_definition=None)

    PipelineRunner._fibo_definition_fallback(term)

    assert term.definition is None
    assert term.definition_source == "document"


def test_fibo_match_without_expected_definition_does_nothing(base_ontology):
    pub = InMemoryPublisher()
    runner = PipelineRunner(ontology=base_ontology, publisher=pub)
    term = _make_term(definition=None, fibo_definition=None)
    term.fibo_match = FIBOMatch(
        uri="https://spec.edmcouncil.org/fibo/CreditRisk",
        match_type="exact",
        expected_definition=None,
    )

    PipelineRunner._fibo_definition_fallback(term)

    assert term.definition is None


# ---------------------------------------------------------------------------
# definition_source tracking
# ---------------------------------------------------------------------------

def test_default_source_is_document():
    record = HarvestRecord(
        text="x",
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="test"),
        tier=Tier.UNSTRUCTURED,
    )
    t = EnrichedTerm.from_harvest(record)
    assert t.definition_source == "document"


def test_source_set_to_fibo_after_fallback(base_ontology):
    pub = InMemoryPublisher()
    term = _make_term(definition="Too short.", fibo_definition=_FIBO_DEF)
    PipelineRunner._fibo_definition_fallback(term)
    assert term.definition_source == "fibo"
