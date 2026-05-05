from __future__ import annotations

import json

import pytest

from ontobridge.agents.harvester import HarvesterAgent, PlainTextReader, CatalogReader
from ontobridge.models import EnrichedTerm
from ontobridge.models.source import HarvestRecord
from ontobridge.models.enums import SourceType, Tier


POLICY_TEXT = """\
Definitions

Retail Customer means a natural person who holds one or more retail banking
products at the institution for personal use across all service channels.

Loan Repayment Schedule means a structured document that governs the periodic
repayment instalments a customer submits against an outstanding loan obligation.

KYC Process means the verification steps applied to assess customer identity
and produce a regulatory compliance record before account onboarding.

ATM Withdrawal means a cash withdrawal operation that uses an ATM channel and
produces a transaction record on the customer account.
"""


@pytest.fixture
def policy_txt(tmp_path):
    f = tmp_path / "CreditPolicy.txt"
    f.write_text(POLICY_TEXT, encoding="utf-8")
    return f


@pytest.fixture
def catalog_json(tmp_path):
    data = [
        {
            "name": "Premium Retail Customer",
            "description": (
                "A retail customer who holds premium credit products with the bank "
                "and uses concierge channels for high-touch service."
            ),
            "schema": "retail",
            "owner": "alice",
        },
        {
            "name": "Joint Account Holder",
            "description": (
                "A retail customer who holds an account jointly with one or more "
                "other parties and submits shared signing instructions."
            ),
            "schema": "deposits",
        },
    ]
    f = tmp_path / "unity_catalog.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Basic harvest from plain text
# ---------------------------------------------------------------------------

class TestHarvestFromText:
    def test_returns_harvest_records(self, policy_txt):
        agent = HarvesterAgent(readers=[PlainTextReader()])
        records = agent.harvest(policy_txt)
        assert all(isinstance(r, HarvestRecord) for r in records)

    def test_extracts_multiple_terms(self, policy_txt):
        agent = HarvesterAgent(readers=[PlainTextReader()])
        records = agent.harvest(policy_txt)
        assert len(records) >= 3

    def test_source_type_is_policy_doc(self, policy_txt):
        agent = HarvesterAgent(readers=[PlainTextReader()])
        records = agent.harvest(policy_txt)
        assert all(r.source_type == SourceType.POLICY_DOC for r in records)

    def test_tier_is_document(self, policy_txt):
        agent = HarvesterAgent(readers=[PlainTextReader()])
        records = agent.harvest(policy_txt)
        assert all(r.tier == Tier.DOCUMENT for r in records)

    def test_source_system_is_stored(self, policy_txt):
        agent = HarvesterAgent(readers=[PlainTextReader()])
        records = agent.harvest(policy_txt, source_system="policy_repo")
        assert all(r.source_ref.source_system == "policy_repo" for r in records)

    def test_document_id_defaults_to_filename(self, policy_txt):
        agent = HarvesterAgent(readers=[PlainTextReader()])
        records = agent.harvest(policy_txt)
        assert all(r.source_ref.document_id == "CreditPolicy.txt" for r in records)

    def test_explicit_document_id_is_used(self, policy_txt):
        agent = HarvesterAgent(readers=[PlainTextReader()])
        records = agent.harvest(policy_txt, document_id="CreditPolicy_v3.pdf")
        assert all(r.source_ref.document_id == "CreditPolicy_v3.pdf" for r in records)

    def test_records_are_deduplicated(self, tmp_path):
        # Same definition text repeated twice should yield only one record
        f = tmp_path / "dup.txt"
        f.write_text(
            "Retail Customer means a natural person who holds retail banking products "
            "for personal use.\n\n"
            "Retail Customer means a natural person who holds retail banking products "
            "for personal use.\n",
            encoding="utf-8",
        )
        agent = HarvesterAgent(readers=[PlainTextReader()])
        records = agent.harvest(f)
        labels = [r.metadata.get("candidate_label") for r in records]
        assert labels.count("Retail Customer") == 1

    def test_candidate_label_in_metadata(self, policy_txt):
        agent = HarvesterAgent(readers=[PlainTextReader()])
        records = agent.harvest(policy_txt)
        labels = [r.metadata.get("candidate_label") for r in records]
        assert any("Retail Customer" in (lbl or "") for lbl in labels)


# ---------------------------------------------------------------------------
# harvest_terms lifts into EnrichedTerm
# ---------------------------------------------------------------------------

class TestHarvestTerms:
    def test_returns_enriched_terms(self, policy_txt):
        agent = HarvesterAgent(readers=[PlainTextReader()])
        terms = agent.harvest_terms(policy_txt)
        assert all(isinstance(t, EnrichedTerm) for t in terms)

    def test_candidate_labels_pre_populated(self, policy_txt):
        agent = HarvesterAgent(readers=[PlainTextReader()])
        terms = agent.harvest_terms(policy_txt)
        assert all(len(t.candidate_labels) > 0 for t in terms)

    def test_preferred_label_matches_extracted_term(self, policy_txt):
        agent = HarvesterAgent(readers=[PlainTextReader()])
        terms = agent.harvest_terms(policy_txt)
        labels = [t.candidate_labels[0].text for t in terms]
        assert any("Retail Customer" in lbl for lbl in labels)

    def test_policy_context_auto_populated(self, policy_txt):
        agent = HarvesterAgent(readers=[PlainTextReader()])
        terms = agent.harvest_terms(policy_txt, document_id="CreditPolicy_v3.pdf")
        for term in terms:
            assert term.policy_context, "policy_context must not be empty"
            ctx = term.policy_context[0]
            assert ctx.document_ref == "CreditPolicy_v3.pdf"
            assert ctx.paragraph  # the definition text

    def test_policy_context_document_ref_falls_back_to_source_system(self, tmp_path):
        # When document_id is not set on the SourceRef, source_system is used
        f = tmp_path / "policy.txt"
        f.write_text(
            "Loan Account means a credit facility extended to a customer under the "
            "terms of a loan agreement with a fixed repayment schedule.\n",
            encoding="utf-8",
        )
        agent = HarvesterAgent(readers=[PlainTextReader()])
        # harvest() uses Path.name as document_id by default
        terms = agent.harvest_terms(f, source_system="policy_repo")
        for term in terms:
            assert term.policy_context
            assert term.policy_context[0].document_ref  # never empty

    def test_governance_r10_does_not_fire_on_harvested_term(self, policy_txt, base_ontology):
        from ontobridge.pipeline import PipelineRunner
        from ontobridge.publisher import InMemoryPublisher

        agent = HarvesterAgent(readers=[PlainTextReader()])
        terms = agent.harvest_terms(policy_txt, document_id="CreditPolicy_v3.pdf")

        pub = InMemoryPublisher()
        runner = PipelineRunner(base_ontology, pub)

        for term in terms:
            published = runner.run(term)
            result = published.enriched_term.governance_result
            if result:
                r10_findings = [
                    f for f in result.findings if f.rule_id == "R10"
                ]
                for finding in r10_findings:
                    assert not finding.triggered, (
                        f"R10 fired on harvested term "
                        f"{term.preferred_label!r} — policy_context not propagated"
                    )


# ---------------------------------------------------------------------------
# Harvest from catalog JSON
# ---------------------------------------------------------------------------

class TestHarvestFromCatalog:
    def test_catalog_source_type(self, catalog_json):
        agent = HarvesterAgent(readers=[CatalogReader()])
        records = agent.harvest(catalog_json)
        assert all(r.source_type == SourceType.CATALOG for r in records)

    def test_catalog_tier_is_structured(self, catalog_json):
        agent = HarvesterAgent(readers=[CatalogReader()])
        records = agent.harvest(catalog_json)
        assert all(r.tier == Tier.STRUCTURED for r in records)

    def test_extracts_both_catalog_entries(self, catalog_json):
        agent = HarvesterAgent(readers=[CatalogReader()])
        records = agent.harvest(catalog_json)
        assert len(records) == 2

    def test_section_reflects_schema(self, catalog_json):
        agent = HarvesterAgent(readers=[CatalogReader()])
        records = agent.harvest(catalog_json)
        sections = {r.source_ref.section for r in records}
        assert "retail" in sections


# ---------------------------------------------------------------------------
# harvest_all deduplicates across sources
# ---------------------------------------------------------------------------

def test_harvest_all_does_not_duplicate_same_file_listed_twice(tmp_path):
    # Listing the same file twice should not double the records
    text = (
        "Retail Customer means a natural person who holds retail banking products "
        "for personal use across all channels.\n"
    )
    f = tmp_path / "policy.txt"
    f.write_text(text, encoding="utf-8")

    agent = HarvesterAgent(readers=[PlainTextReader()])
    records = agent.harvest_all([f, f])
    labels = [r.metadata.get("candidate_label") for r in records]
    assert labels.count("Retail Customer") == 1


def test_harvest_all_collects_from_multiple_sources(tmp_path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text(
        "Loan Account means a credit facility extended to a customer under the "
        "terms of a loan agreement with fixed repayment schedule.\n",
        encoding="utf-8",
    )
    f2.write_text(
        "KYC Process means a regulatory compliance check applied before "
        "customer onboarding to verify identity and assess risk profile.\n",
        encoding="utf-8",
    )
    agent = HarvesterAgent(readers=[PlainTextReader()])
    records = agent.harvest_all([f1, f2])
    assert len(records) == 2


# ---------------------------------------------------------------------------
# Reader dispatch
# ---------------------------------------------------------------------------

def test_no_reader_raises_value_error(tmp_path):
    f = tmp_path / "data.parquet"
    f.write_bytes(b"fake")
    agent = HarvesterAgent(readers=[PlainTextReader()])
    with pytest.raises(ValueError, match="No reader registered"):
        agent.harvest(f)


def test_default_readers_cover_txt_json_csv(tmp_path):
    agent = HarvesterAgent()
    assert agent._find_reader(tmp_path / "p.txt") is not None
    assert agent._find_reader(tmp_path / "c.json") is not None
    assert agent._find_reader(tmp_path / "c.csv") is not None


# ---------------------------------------------------------------------------
# Custom extractor plug-in
# ---------------------------------------------------------------------------

def test_custom_extractor_is_used(tmp_path, policy_txt):
    from ontobridge.agents.harvester.protocols import ExtractedTerm, RawDocument

    class FixedExtractor:
        def extract(self, doc: RawDocument) -> list[ExtractedTerm]:
            return [
                ExtractedTerm(
                    candidate_label="Custom Term",
                    definition=(
                        "A term always returned by the custom extractor regardless "
                        "of document content."
                    ),
                )
            ]

    agent = HarvesterAgent(readers=[PlainTextReader()], extractor=FixedExtractor())
    records = agent.harvest(policy_txt)
    # Every doc chunk should yield exactly "Custom Term"
    labels = {r.metadata.get("candidate_label") for r in records}
    assert labels == {"Custom Term"}


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

def test_plain_text_reader_satisfies_document_reader_protocol():
    from ontobridge.agents.harvester.protocols import DocumentReader
    assert isinstance(PlainTextReader(), DocumentReader)


def test_catalog_reader_satisfies_document_reader_protocol():
    from ontobridge.agents.harvester.protocols import DocumentReader
    assert isinstance(CatalogReader(), DocumentReader)


def test_pattern_extractor_satisfies_term_extractor_protocol():
    from ontobridge.agents.harvester.protocols import TermExtractor
    from ontobridge.agents.harvester.extractors.pattern import PatternTermExtractor
    assert isinstance(PatternTermExtractor(), TermExtractor)
