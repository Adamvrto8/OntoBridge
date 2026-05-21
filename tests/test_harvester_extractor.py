from __future__ import annotations

import pytest

from ontobridge.agents.harvester.extractors.pattern import PatternTermExtractor
from ontobridge.agents.harvester.protocols import RawDocument


@pytest.fixture
def extractor():
    return PatternTermExtractor()


# ---------------------------------------------------------------------------
# "means" pattern
# ---------------------------------------------------------------------------

def test_means_pattern_extracts_label_and_definition(extractor):
    doc = RawDocument(
        text=(
            "Retail customer means a natural person who holds banking products "
            "with the institution for personal use."
        )
    )
    results = extractor.extract(doc)
    assert len(results) == 1
    assert results[0].candidate_label == "Retail customer"
    assert "natural person" in results[0].definition


def test_shall_mean_variant(extractor):
    doc = RawDocument(
        text=(
            "Joint Account Holder shall mean a person who shares an account "
            "with one or more other parties and holds joint signing authority."
        )
    )
    results = extractor.extract(doc)
    assert results
    assert results[0].candidate_label == "Joint Account Holder"


def test_refers_to_variant(extractor):
    doc = RawDocument(
        text=(
            "KYC process refers to the verification steps applied to a customer "
            "before onboarding to satisfy regulatory requirements."
        )
    )
    results = extractor.extract(doc)
    assert results
    assert "KYC process" in results[0].candidate_label


def test_is_defined_as_variant(extractor):
    doc = RawDocument(
        text=(
            "Premium Customer is defined as a retail customer who holds premium "
            "credit products and uses concierge service channels."
        )
    )
    results = extractor.extract(doc)
    assert results
    assert results[0].candidate_label == "Premium Customer"


# ---------------------------------------------------------------------------
# Colon (glossary) pattern
# ---------------------------------------------------------------------------

def test_colon_pattern_extracts_term(extractor):
    doc = RawDocument(
        text=(
            "Loan Repayment Schedule: A document that governs the periodic "
            "repayment instalments a customer submits against an outstanding loan."
        )
    )
    results = extractor.extract(doc)
    assert results
    assert results[0].candidate_label == "Loan Repayment Schedule"
    assert "instalments" in results[0].definition


def test_catalog_style_colon_entry(extractor):
    doc = RawDocument(
        text=(
            "retail_customer: A natural person who holds retail products at the "
            "bank for personal use across all channels."
        ),
        metadata={"schema": "retail"},
    )
    # Lower-case first letter means the pattern won't match — expected; catalog
    # rows are uppercased by CatalogReader before extraction
    # (Verify no crash and empty result is fine)
    results = extractor.extract(doc)
    # Either matched or not — just verify no exception
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Confidence and section inheritance
# ---------------------------------------------------------------------------

def test_confidence_is_within_range(extractor):
    doc = RawDocument(
        text=(
            "ATM Withdrawal means a cash withdrawal operation that uses an ATM "
            "channel and produces a transaction record on the customer account."
        )
    )
    results = extractor.extract(doc)
    assert results
    assert 0.0 <= results[0].confidence <= 1.0


def test_section_is_inherited_from_doc(extractor):
    doc = RawDocument(
        text=(
            "Credit Limit means the maximum outstanding balance permitted on a "
            "credit product as approved by the credit committee."
        ),
        section="Credit Policy §3.2",
    )
    results = extractor.extract(doc)
    assert results
    assert results[0].section == "Credit Policy §3.2"


def test_metadata_is_copied_from_doc(extractor):
    doc = RawDocument(
        text=(
            "Overdraft Facility means a short-term credit arrangement permitting "
            "a customer to draw funds beyond the account balance up to an approved limit."
        ),
        metadata={"owner": "risk_team"},
    )
    results = extractor.extract(doc)
    assert results
    assert results[0].metadata.get("owner") == "risk_team"


# ---------------------------------------------------------------------------
# Deduplication within a single document
# ---------------------------------------------------------------------------

def test_same_label_not_extracted_twice(extractor):
    doc = RawDocument(
        text=(
            "Retail customer means a person holding retail products. "
            "Retail customer means a person holding retail products at the bank."
        )
    )
    results = extractor.extract(doc)
    labels = [r.candidate_label for r in results]
    assert labels.count("Retail customer") == 1


# ---------------------------------------------------------------------------
# Noise rejection
# ---------------------------------------------------------------------------

def test_short_definition_rejected(extractor):
    doc = RawDocument(text="KYC means compliance check.")
    results = extractor.extract(doc)
    assert not results


def test_long_label_not_extracted(extractor):
    doc = RawDocument(
        text=(
            "This policy document means that all retail banking products offered "
            "to customers must comply with the applicable regulatory framework."
        )
    )
    results = extractor.extract(doc)
    # Label would be > 7 words — should be rejected
    assert not results


def test_empty_document_returns_empty(extractor):
    assert extractor.extract(RawDocument(text="")) == []


def test_plain_sentence_without_trigger_returns_empty(extractor):
    doc = RawDocument(
        text="The bank offers a variety of retail products to its customers."
    )
    assert extractor.extract(doc) == []


# ---------------------------------------------------------------------------
# New pattern coverage: acronyms, numbered lists, multi-line, lowercase
# ---------------------------------------------------------------------------

def test_term_with_parenthetical_acronym_means(extractor):
    """'Term (ACR) means ...' — acronym stripped from label."""
    doc = RawDocument(
        text=(
            "Anti-Money Laundering (AML) means the set of laws, regulations, "
            "and procedures intended to prevent criminals from concealing illegally obtained funds."
        )
    )
    results = extractor.extract(doc)
    assert results
    assert results[0].candidate_label == "Anti-Money Laundering"
    assert "regulations" in results[0].definition


def test_term_with_parenthetical_acronym_colon(extractor):
    """'Term (ACR): Definition' — acronym stripped, definition captured."""
    doc = RawDocument(
        text=(
            "Know Your Customer (KYC): A mandatory due-diligence process "
            "that banks use to verify customer identity before onboarding."
        )
    )
    results = extractor.extract(doc)
    assert results
    assert results[0].candidate_label == "Know Your Customer"
    assert "identity" in results[0].definition


def test_numbered_list_item_extracted(extractor):
    """'1. Term means Definition' — numbered list items should be extracted."""
    doc = RawDocument(
        text=(
            "1. Credit Risk means the probability of financial loss arising "
            "from a borrower's failure to meet their repayment obligations."
        )
    )
    results = extractor.extract(doc)
    assert results
    assert results[0].candidate_label == "Credit Risk"
    assert "probability" in results[0].definition


def test_multiline_definition_joined(extractor):
    """'Term:\\n  Definition' — colon-newline entries should be joined and extracted."""
    doc = RawDocument(
        text=(
            "KYC:\n"
            "  The process of verifying customer identity before onboarding "
            "to satisfy regulatory anti-money laundering requirements."
        )
    )
    results = extractor.extract(doc)
    assert results
    assert results[0].candidate_label == "KYC"
    assert "identity" in results[0].definition


def test_lowercase_term_with_acronym(extractor):
    """'lowercase term (ACR), which is ...' — lowercase form with acronym."""
    doc = RawDocument(
        text=(
            "anti-money laundering (AML), which is a regulatory framework "
            "designed to detect and prevent criminal financial activity in banking."
        )
    )
    results = extractor.extract(doc)
    assert results
    assert results[0].candidate_label == "anti-money laundering"
    assert "regulatory" in results[0].definition
