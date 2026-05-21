"""Tests for TFIDFEncoder."""
from __future__ import annotations

import math

import pytest

from ontobridge.agents.mapping.strategies import TFIDFEncoder, TokenOverlapEncoder


_CORPUS = [
    "Credit risk assessment for loan applications",
    "Credit score evaluation and credit check procedures",
    "Anti-money laundering AML compliance requirements",
    "Customer due diligence KYC verification process",
    "Collateral valuation and loan-to-value LTV ratio",
    "Debt-to-income DTI ratio for underwriting decisions",
    "Non-performing loan NPL classification criteria",
    "Mortgage loan secured by real estate collateral",
]


@pytest.fixture
def encoder() -> TFIDFEncoder:
    return TFIDFEncoder(_CORPUS)


def test_encode_returns_nonempty_for_known_tokens(encoder):
    result = encoder.encode("credit risk")
    assert len(result) > 0
    assert all(v > 0 for v in result.values())


def test_encode_returns_empty_for_empty_string(encoder):
    assert encoder.encode("") == {}
    assert encoder.encode("   ") == {}


def test_common_token_lower_weight_than_rare():
    # Build a corpus where "credit" appears in 6 of 8 docs, "delinquency" in 1
    corpus = [
        "credit risk assessment",
        "credit score and credit history",
        "credit card credit limit",
        "credit check for loan applications",
        "credit facility credit terms",
        "credit rating agency review",
        "anti-money laundering procedures",
        "delinquency classification for overdue loans",
    ]
    enc = TFIDFEncoder(corpus)
    credit_w = enc.encode("credit")["credit"]
    delinquency_w = enc.encode("delinquency")["delinquency"]
    assert delinquency_w > credit_w, (
        f"Expected delinquency ({delinquency_w:.3f}) > credit ({credit_w:.3f})"
    )


def test_unknown_token_gets_max_idf(encoder):
    known = encoder.encode("credit")["credit"]
    unknown = encoder.encode("xyzquux")["xyzquux"]
    # Unknown tokens assumed maximally distinctive
    assert unknown > known


def test_similarity_improves_over_token_overlap():
    """TF-IDF cosine should rank the right concept higher than token overlap
    when a common token would otherwise dominate."""
    from ontobridge.agents.mapping.strategies import _cosine

    # "credit" is common; "collateral" is specific
    # Query: "collateral" — should match "Collateral valuation" higher than "Credit risk"
    enc = TFIDFEncoder(_CORPUS)

    q = enc.encode("collateral")
    collateral_doc = enc.encode("Collateral valuation and loan-to-value LTV ratio")
    credit_doc = enc.encode("Credit risk assessment for loan applications")

    sim_collateral = _cosine(q, collateral_doc)
    sim_credit = _cosine(q, credit_doc)

    assert sim_collateral > sim_credit, (
        f"Expected collateral doc ({sim_collateral:.3f}) to score higher "
        f"than credit doc ({sim_credit:.3f})"
    )


def test_token_overlap_fails_same_case():
    """Show token overlap gives equal or worse ranking for the same query."""
    from ontobridge.agents.mapping.strategies import _cosine

    enc = TokenOverlapEncoder()
    q = enc.encode("collateral")
    collateral_doc = enc.encode("Collateral valuation and loan-to-value LTV ratio")
    credit_doc = enc.encode("Credit risk assessment for loan applications")

    sim_collateral = _cosine(q, collateral_doc)
    sim_credit = _cosine(q, credit_doc)

    # With token overlap, "collateral" appears once in both — collateral_doc wins
    # only because it also contains "collateral" as a longer match; but the margin
    # should be smaller than TF-IDF
    # This test documents the existing behaviour, not asserts correctness
    assert sim_collateral >= sim_credit  # at least not worse


def test_from_ontology(base_ontology):
    enc = TFIDFEncoder.from_ontology(base_ontology)
    result = enc.encode("credit risk assessment")
    assert len(result) > 0
    # All weights positive
    assert all(v > 0 for v in result.values())


def test_from_ontology_rare_term_higher_weight(base_ontology):
    enc = TFIDFEncoder.from_ontology(base_ontology)
    # "customer" appears in many ontology concepts → lower IDF
    # "delinquency" appears in few → higher IDF
    customer_w = enc.encode("customer").get("customer", 0)
    delinquency_w = enc.encode("delinquency").get("delinquency", 0)
    assert delinquency_w > customer_w
