"""Tests for TFIDFPolicyLinker."""
from __future__ import annotations

import pytest

from ontobridge.agents.policy_linker.tfidf import TFIDFPolicyLinker
from ontobridge.models import (
    CandidateLabel,
    EnrichedTerm,
    HarvestRecord,
    SourceRef,
    SourceType,
    Tier,
)


def _make_term(label: str, definition: str) -> EnrichedTerm:
    record = HarvestRecord(
        text=definition,
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="test.txt"),
        tier=Tier.DOCUMENT,
    )
    term = EnrichedTerm.from_harvest(record)
    term.candidate_labels = [CandidateLabel(text=label, confidence=0.9)]
    term.definition = definition
    return term


def test_index_and_find():
    linker = TFIDFPolicyLinker(threshold=0.05)
    linker.index_text(
        "Anti-money laundering (AML) procedures require banks to identify customers.",
        document_ref="aml_policy.pdf",
    )
    matches = linker.find("anti-money laundering AML customer identification")
    assert len(matches) > 0
    assert matches[0].document_ref == "aml_policy.pdf"
    assert matches[0].similarity > 0.05


def test_apply_populates_policy_context():
    linker = TFIDFPolicyLinker(threshold=0.05)
    linker.index_text(
        "A loan is a sum of money borrowed from a bank at an agreed interest rate.",
        document_ref="credit_policy.pdf",
    )
    term = _make_term("Loan", "A sum of money borrowed from a financial institution.")
    assert len(term.policy_context) == 0
    linker.apply(term)
    assert len(term.policy_context) > 0
    assert term.policy_context[0].document_ref == "credit_policy.pdf"


def test_apply_does_not_duplicate_context():
    linker = TFIDFPolicyLinker(threshold=0.05)
    linker.index_text("Loan repayment schedules define periodic payment dates.", "policy.pdf")
    term = _make_term("Loan repayment", "Schedule of periodic loan payments.")
    linker.apply(term)
    count_after_first = len(term.policy_context)
    linker.apply(term)
    assert len(term.policy_context) == count_after_first


def test_empty_store_returns_no_matches():
    linker = TFIDFPolicyLinker()
    matches = linker.find("credit risk assessment")
    assert matches == []


def test_below_threshold_not_returned():
    linker = TFIDFPolicyLinker(threshold=0.99)
    linker.index_text("Completely unrelated content about weather forecasting.", "doc.pdf")
    matches = linker.find("anti-money laundering financial crime")
    assert matches == []


def test_count():
    linker = TFIDFPolicyLinker()
    assert linker.count() == 0
    linker.index_text("First paragraph about banking regulations and compliance.", "doc.pdf")
    linker.index_text("Second paragraph about credit risk and loan assessment.", "doc.pdf")
    assert linker.count() == 2


def test_deduplication():
    linker = TFIDFPolicyLinker()
    text = "Anti-money laundering procedures are mandatory for all banks."
    linker.index_text(text, "doc.pdf")
    linker.index_text(text, "doc.pdf")  # same text, same ref
    assert linker.count() == 1


def test_threshold_validation():
    with pytest.raises(ValueError):
        TFIDFPolicyLinker(threshold=1.5)
    with pytest.raises(ValueError):
        TFIDFPolicyLinker(threshold=-0.1)
