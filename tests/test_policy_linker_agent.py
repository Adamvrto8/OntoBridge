from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping

import pytest

from ontobridge.agents.policy_linker.agent import PolicyLinkerAgent, _to_dense
from ontobridge.agents.policy_linker.store import InMemoryVectorStore
from ontobridge.models import CandidateLabel, EnrichedTerm
from ontobridge.models.enrichment import PolicyContext
from ontobridge.models.enums import SourceType
from ontobridge.models.source import HarvestRecord, SourceRef


# ---------------------------------------------------------------------------
# Fake encoder — returns {str(i): float} with 4 dimensions, text-sensitive
# ---------------------------------------------------------------------------

class FakeEncoder:
    """Deterministic 4-dim dense encoder with non-negative components.

    All components are in [0, 1] so the cosine similarity between any two
    vectors is always >= 0.  This makes threshold=0.0 predictable in tests.
    """

    def encode(self, text: str) -> dict[str, float]:
        seed = sum(ord(c) for c in text)
        raw = [abs(math.sin(seed * 0.7 + i * 1.3)) + 0.01 for i in range(4)]
        norm = math.sqrt(sum(v * v for v in raw))
        return {str(i): v / norm for i, v in enumerate(raw)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_term(label: str, definition: str = "") -> EnrichedTerm:
    record = HarvestRecord(
        text=definition or label,
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test"),
    )
    term = EnrichedTerm.from_harvest(record)
    term.candidate_labels = [CandidateLabel(text=label, confidence=0.9)]
    term.definition = definition or None
    return term


def _make_agent(threshold: float = 0.0) -> PolicyLinkerAgent:
    return PolicyLinkerAgent(
        store=InMemoryVectorStore(),
        encoder=FakeEncoder(),
        threshold=threshold,
        top_k=3,
    )


# ---------------------------------------------------------------------------
# _to_dense
# ---------------------------------------------------------------------------

def test_to_dense_ordering():
    mapping = {"0": 0.1, "1": 0.2, "2": 0.3}
    assert _to_dense(mapping) == [0.1, 0.2, 0.3]


def test_to_dense_single():
    assert _to_dense({"0": 1.0}) == [1.0]


# ---------------------------------------------------------------------------
# PolicyLinkerAgent — constructor
# ---------------------------------------------------------------------------

def test_invalid_threshold():
    with pytest.raises(ValueError, match="threshold"):
        PolicyLinkerAgent(InMemoryVectorStore(), FakeEncoder(), threshold=1.5)


# ---------------------------------------------------------------------------
# index_document
# ---------------------------------------------------------------------------

def test_index_text_file(tmp_path: Path):
    doc = tmp_path / "policy.txt"
    doc.write_text("Credit risk is the risk of borrower default.\nLiquidity risk arises from mismatched maturities.")
    agent = _make_agent()
    count = agent.index_document(doc)
    assert count > 0
    assert agent._store.count() > 0


def test_index_uses_basename_as_ref(tmp_path: Path):
    doc = tmp_path / "CreditPolicy.txt"
    doc.write_text("Some policy text about loans and credit.")
    agent = _make_agent()
    agent.index_document(doc)
    results = agent.find("credit", top_k=5)
    assert all(r.document_ref == "CreditPolicy.txt" for r in results)


def test_index_uses_custom_ref(tmp_path: Path):
    doc = tmp_path / "policy.txt"
    doc.write_text("Loan application must be reviewed.")
    agent = _make_agent()
    agent.index_document(doc, document_ref="CreditPolicy_v3.pdf#section-2.1")
    results = agent.find("loan", top_k=5)
    assert all(r.document_ref == "CreditPolicy_v3.pdf#section-2.1" for r in results)


def test_index_twice_same_file_is_idempotent(tmp_path: Path):
    doc = tmp_path / "policy.txt"
    doc.write_text("Only one line of policy text.")
    agent = _make_agent()
    agent.index_document(doc)
    count_first = agent._store.count()
    agent.index_document(doc)
    assert agent._store.count() == count_first


def test_index_empty_file_returns_zero(tmp_path: Path):
    doc = tmp_path / "empty.txt"
    doc.write_text("")
    agent = _make_agent()
    assert agent.index_document(doc) == 0


def test_index_unsupported_format_raises(tmp_path: Path):
    doc = tmp_path / "data.xyz"
    doc.write_text("irrelevant")
    agent = _make_agent()
    with pytest.raises(ValueError, match="No reader"):
        agent.index_document(doc)


# ---------------------------------------------------------------------------
# find
# ---------------------------------------------------------------------------

def test_find_empty_store():
    agent = _make_agent()
    assert agent.find("credit risk") == []


def test_find_returns_matches_above_threshold(tmp_path: Path):
    doc = tmp_path / "policy.txt"
    doc.write_text("Credit risk is the risk of borrower default.")
    agent = PolicyLinkerAgent(InMemoryVectorStore(), FakeEncoder(), threshold=0.0, top_k=3)
    agent.index_document(doc)
    results = agent.find("credit risk")
    assert len(results) > 0


def test_find_threshold_filters(tmp_path: Path):
    doc = tmp_path / "policy.txt"
    doc.write_text("Credit risk is the risk of borrower default.")
    # threshold 1.0 means only perfect cosine matches pass
    agent = PolicyLinkerAgent(InMemoryVectorStore(), FakeEncoder(), threshold=1.0, top_k=3)
    agent.index_document(doc)
    results = agent.find("credit risk")
    assert results == []


def test_find_top_k_override(tmp_path: Path):
    doc = tmp_path / "policy.txt"
    lines = "\n".join(f"Policy sentence number {i}." for i in range(10))
    doc.write_text(lines)
    agent = PolicyLinkerAgent(InMemoryVectorStore(), FakeEncoder(), threshold=0.0, top_k=10)
    agent.index_document(doc)
    results = agent.find("policy sentence", top_k=2)
    assert len(results) <= 2


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def test_apply_populates_policy_context(tmp_path: Path):
    doc = tmp_path / "policy.txt"
    doc.write_text("Retail PI Customer is a customer in the personal instalment segment.")
    agent = PolicyLinkerAgent(InMemoryVectorStore(), FakeEncoder(), threshold=0.0, top_k=3)
    agent.index_document(doc)
    term = _make_term("Retail PI Customer", "A customer in the PI segment.")
    agent.apply(term)
    assert len(term.policy_context) > 0


def test_apply_empty_store_leaves_context_empty():
    agent = _make_agent(threshold=0.0)
    term = _make_term("Loan Application", "A request for credit.")
    agent.apply(term)
    assert term.policy_context == []


def test_apply_is_nondestructive(tmp_path: Path):
    doc = tmp_path / "policy.txt"
    doc.write_text("Credit scoring determines eligibility.")
    agent = PolicyLinkerAgent(InMemoryVectorStore(), FakeEncoder(), threshold=0.0, top_k=3)
    agent.index_document(doc)

    term = _make_term("Credit Score", "Creditworthiness measure.")
    pre_existing = PolicyContext(
        paragraph="Manual source.",
        document_ref="Manual.pdf",
        chunk_id="manual-000",
    )
    term.policy_context.append(pre_existing)

    agent.apply(term)
    assert pre_existing in term.policy_context


def test_apply_deduplicates_on_second_call(tmp_path: Path):
    doc = tmp_path / "policy.txt"
    doc.write_text("Loan application must include income proof.")
    agent = PolicyLinkerAgent(InMemoryVectorStore(), FakeEncoder(), threshold=0.0, top_k=3)
    agent.index_document(doc)

    term = _make_term("Loan Application", "A formal credit request.")
    agent.apply(term)
    count_after_first = len(term.policy_context)
    agent.apply(term)
    assert len(term.policy_context) == count_after_first


def test_apply_no_label_no_query():
    agent = _make_agent(threshold=0.0)
    record = HarvestRecord(
        text="text",
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test"),
    )
    term = EnrichedTerm.from_harvest(record)
    # no labels, no definition
    agent.apply(term)
    assert term.policy_context == []


def test_apply_sets_policy_context_fields(tmp_path: Path):
    doc = tmp_path / "CreditPolicy.txt"
    doc.write_text("The gross income criterion applies to all loan applicants.")
    agent = PolicyLinkerAgent(InMemoryVectorStore(), FakeEncoder(), threshold=0.0, top_k=3)
    agent.index_document(doc, document_ref="CreditPolicy_v3.pdf")
    term = _make_term("Gross Income", "Primary eligibility criterion for loans.")
    agent.apply(term)
    ctx = term.policy_context[0]
    assert ctx.document_ref == "CreditPolicy_v3.pdf"
    assert ctx.paragraph != ""
    assert ctx.chunk_id is not None
    assert ctx.similarity is not None
    assert 0.0 <= ctx.similarity <= 1.0
