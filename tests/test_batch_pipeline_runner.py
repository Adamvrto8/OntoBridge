from __future__ import annotations

from pathlib import Path

import pytest

from ontobridge.batch import BatchPipelineRunner, BatchResult, FailedTerm
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
from ontobridge.publisher import InMemoryPublisher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_term(
    label: str = "Premium retail customer",
    definition: str = (
        "A retail customer who holds premium credit products with the bank "
        "and uses concierge channels for high-touch service."
    ),
    policy_doc: str = "CreditPolicy_v3.pdf",
    section: str = "4.2",
) -> EnrichedTerm:
    harvest = HarvestRecord(
        text=definition,
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(
            source_system="test",
            document_id=policy_doc,
            section=section,
        ),
        tier=Tier.DOCUMENT,
    )
    term = EnrichedTerm.from_harvest(harvest)
    term.candidate_labels = [CandidateLabel(text=label, confidence=0.95)]
    term.definition = definition
    term.policy_context = [
        PolicyContext(
            paragraph=definition,
            document_ref=policy_doc,
            section=section,
        )
    ]
    return term


POLICY_TEXT = """\
Definitions

Retail Customer means a natural person who holds one or more retail banking
products at the institution for personal use across all service channels.

Loan Repayment Schedule means a structured document that governs the periodic
repayment instalments a customer submits against an outstanding loan obligation.

KYC Process means the verification steps applied to assess customer identity
and produce a regulatory compliance record before account onboarding.
"""


@pytest.fixture
def policy_txt(tmp_path) -> Path:
    f = tmp_path / "CreditPolicy.txt"
    f.write_text(POLICY_TEXT, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# BatchResult dataclass
# ---------------------------------------------------------------------------

class TestBatchResult:
    def test_total_counts_all_buckets(self):
        r = BatchResult()
        r.published.append(object())  # type: ignore[arg-type]
        r.skipped.append((object(), "reason"))  # type: ignore[arg-type]
        r.failed.append(object())  # type: ignore[arg-type]
        assert r.total == 3

    def test_success_rate_all_published(self):
        r = BatchResult()
        r.published = [object(), object()]  # type: ignore[list-item]
        assert r.success_rate == 1.0

    def test_success_rate_empty(self):
        assert BatchResult().success_rate == 0.0

    def test_success_rate_partial(self):
        r = BatchResult()
        r.published = [object()]  # type: ignore[list-item]
        r.skipped = [(object(), "x")]  # type: ignore[list-item]
        assert r.success_rate == 0.5

    def test_summary_contains_counts(self):
        r = BatchResult()
        r.published = [object(), object()]  # type: ignore[list-item]
        r.skipped = [(object(), "x")]  # type: ignore[list-item]
        s = r.summary()
        assert "2 published" in s
        assert "1 skipped" in s
        assert "0 failed" in s


# ---------------------------------------------------------------------------
# run_terms — success path
# ---------------------------------------------------------------------------

class TestRunTermsSuccess:
    def test_single_clean_term_is_published(self, base_ontology):
        pub = InMemoryPublisher()
        runner = BatchPipelineRunner(base_ontology, pub)
        result = runner.run_terms([_make_term()])
        assert len(result.published) == 1
        assert len(result.skipped) == 0
        assert len(result.failed) == 0

    def test_multiple_clean_terms_all_published(self, base_ontology):
        pub = InMemoryPublisher()
        runner = BatchPipelineRunner(base_ontology, pub)
        terms = [
            _make_term("Premium retail customer"),
            _make_term(
                "Loan Repayment Schedule",
                definition=(
                    "A document that governs the periodic repayment instalments "
                    "a customer submits against an outstanding loan obligation."
                ),
                section="5.4",
            ),
        ]
        result = runner.run_terms(terms)
        assert len(result.published) == 2
        assert result.success_rate == 1.0

    def test_published_terms_are_in_publisher(self, base_ontology):
        pub = InMemoryPublisher()
        runner = BatchPipelineRunner(base_ontology, pub)
        runner.run_terms([_make_term()], approved_by="alice")
        assert len(pub.search_terms("")) == 1

    def test_approved_by_forwarded_to_published_term(self, base_ontology):
        pub = InMemoryPublisher()
        runner = BatchPipelineRunner(base_ontology, pub)
        result = runner.run_terms([_make_term()], approved_by="alice.steward")
        assert result.published[0].approved_by == "alice.steward"

    def test_empty_list_returns_empty_result(self, base_ontology):
        result = BatchPipelineRunner(base_ontology, InMemoryPublisher()).run_terms([])
        assert result.total == 0

    def test_result_is_batch_result_instance(self, base_ontology):
        result = BatchPipelineRunner(
            base_ontology, InMemoryPublisher()
        ).run_terms([_make_term()])
        assert isinstance(result, BatchResult)


# ---------------------------------------------------------------------------
# run_terms — error handling
# ---------------------------------------------------------------------------

class TestRunTermsErrors:
    def test_term_missing_labels_is_skipped_not_failed(self, base_ontology):
        pub = InMemoryPublisher()
        runner = BatchPipelineRunner(base_ontology, pub)
        bad = _make_term()
        bad.candidate_labels = []
        result = runner.run_terms([bad])
        assert len(result.skipped) == 1
        assert len(result.failed) == 0

    def test_term_missing_definition_is_skipped_not_failed(self, base_ontology):
        pub = InMemoryPublisher()
        runner = BatchPipelineRunner(base_ontology, pub)
        bad = _make_term()
        bad.definition = ""
        result = runner.run_terms([bad])
        assert len(result.skipped) == 1

    def test_duplicate_uri_is_skipped(self, base_ontology):
        pub = InMemoryPublisher()
        runner = BatchPipelineRunner(base_ontology, pub)
        term = _make_term()
        # First run publishes it; second run hits duplicate URI in publisher
        runner.run_terms([term], approved_by="alice")
        result = runner.run_terms([_make_term()], approved_by="alice")
        assert len(result.skipped) == 1
        assert len(result.failed) == 0

    def test_one_bad_term_does_not_abort_remaining(self, base_ontology):
        pub = InMemoryPublisher()
        runner = BatchPipelineRunner(base_ontology, pub)
        bad = _make_term()
        bad.candidate_labels = []
        good = _make_term(
            "Loan Repayment Schedule",
            definition=(
                "A structured document that governs the periodic repayment instalments "
                "a customer submits against an outstanding loan obligation."
            ),
            section="5.4",
        )
        result = runner.run_terms([bad, good])
        assert len(result.published) == 1
        assert len(result.skipped) == 1

    def test_unexpected_exception_goes_to_failed(self, base_ontology, monkeypatch):
        pub = InMemoryPublisher()
        runner = BatchPipelineRunner(base_ontology, pub)

        def boom(term, *, term_uri=None, approved_by=None):
            raise RuntimeError("unexpected database error")

        monkeypatch.setattr(runner._runner, "run", boom)
        result = runner.run_terms([_make_term()])
        assert len(result.failed) == 1
        assert result.failed[0].error_type == "RuntimeError"
        assert "unexpected database error" in result.failed[0].error

    def test_failed_term_contains_original_term(self, base_ontology, monkeypatch):
        pub = InMemoryPublisher()
        runner = BatchPipelineRunner(base_ontology, pub)
        term = _make_term()

        monkeypatch.setattr(runner._runner, "run", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        result = runner.run_terms([term])
        assert result.failed[0].term is term


# ---------------------------------------------------------------------------
# run_document — from file
# ---------------------------------------------------------------------------

class TestRunDocument:
    def test_run_document_extracts_and_publishes_terms(self, base_ontology, policy_txt):
        pub = InMemoryPublisher()
        runner = BatchPipelineRunner(base_ontology, pub)
        result = runner.run_document(policy_txt, source_system="policy_repo")
        assert result.total > 0
        # At least some terms should make it through
        assert len(result.published) + len(result.skipped) == result.total

    def test_run_document_returns_batch_result(self, base_ontology, policy_txt):
        result = BatchPipelineRunner(
            base_ontology, InMemoryPublisher()
        ).run_document(policy_txt)
        assert isinstance(result, BatchResult)

    def test_run_documents_multiple_files(self, base_ontology, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text(
            "Loan Account means a credit facility extended to a customer under the "
            "terms of a loan agreement with a fixed repayment schedule.\n",
            encoding="utf-8",
        )
        f2.write_text(
            "KYC Process means a regulatory compliance check applied before customer "
            "onboarding to verify identity and assess risk profile thoroughly.\n",
            encoding="utf-8",
        )
        pub = InMemoryPublisher()
        runner = BatchPipelineRunner(base_ontology, pub)
        result = runner.run_documents([f1, f2])
        assert result.total == 2

    def test_run_documents_deduplicates_same_file_twice(self, base_ontology, policy_txt):
        pub = InMemoryPublisher()
        runner = BatchPipelineRunner(base_ontology, pub)
        result = runner.run_documents([policy_txt, policy_txt])
        # Listing the same file twice must not double the terms
        single = BatchPipelineRunner(base_ontology, InMemoryPublisher()).run_document(policy_txt)
        assert result.total == single.total


# ---------------------------------------------------------------------------
# Progress callback
# ---------------------------------------------------------------------------

def test_progress_callback_called_for_each_term(base_ontology):
    calls: list[tuple[int, int]] = []

    def cb(processed: int, total: int) -> None:
        calls.append((processed, total))

    terms = [
        _make_term("Premium retail customer"),
        _make_term(
            "Loan Repayment Schedule",
            definition=(
                "A structured document governing periodic repayment instalments "
                "submitted by a customer against an outstanding loan obligation."
            ),
            section="5.4",
        ),
    ]
    runner = BatchPipelineRunner(base_ontology, InMemoryPublisher(), on_progress=cb)
    runner.run_terms(terms)
    assert len(calls) == 2
    assert calls[0] == (1, 2)
    assert calls[1] == (2, 2)


# ---------------------------------------------------------------------------
# Custom harvester plug-in
# ---------------------------------------------------------------------------

def test_custom_harvester_is_used(base_ontology, tmp_path):
    from ontobridge.agents.harvester.protocols import ExtractedTerm, RawDocument
    from ontobridge.agents.harvester import HarvesterAgent, PlainTextReader

    class FixedExtractor:
        def extract(self, doc: RawDocument) -> list[ExtractedTerm]:
            return [
                ExtractedTerm(
                    candidate_label="Retail Customer",
                    definition=(
                        "A natural person who holds retail banking products at the "
                        "institution for personal use across all service channels."
                    ),
                )
            ]

    harvester = HarvesterAgent(
        readers=[PlainTextReader()],
        extractor=FixedExtractor(),
    )
    f = tmp_path / "doc.txt"
    f.write_text("anything", encoding="utf-8")

    pub = InMemoryPublisher()
    runner = BatchPipelineRunner(base_ontology, pub, harvester=harvester)
    result = runner.run_document(f)
    labels = [p.enriched_term.preferred_label for p in result.published]
    assert any("Retail Customer" in (lbl or "") for lbl in labels)
