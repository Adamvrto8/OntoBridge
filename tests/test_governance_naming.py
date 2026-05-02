from __future__ import annotations

from ontobridge.agents.governance.models import Candidate, Severity
from ontobridge.agents.governance.rules.naming import (
    Rule04UserRejectedSynonym,
    Rule05CrossDomainCompatibleMatch,
    Rule06UppercaseShortNoContext,
    Rule07SingleNounNoQualifier,
)

PI_SCHEME = "http://ontobridge.dev/ontology/bank/SchemeParty"


# ------------------- Rule 4: user rejected synonym -> domain prefix -------------------

def test_r4_applies_domain_prefix_when_rejected(base_ontology):
    rule = Rule04UserRejectedSynonym()
    cand = Candidate(
        preferred_label="GI",
        domain_code="Retail_PI",
        user_rejected_synonym=True,
    )
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered
    assert finding.suggestions["skos:prefLabel"] == "Retail_PI.GI"


def test_r4_blocks_when_no_domain(base_ontology):
    rule = Rule04UserRejectedSynonym()
    cand = Candidate(preferred_label="GI", user_rejected_synonym=True)
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered
    assert finding.severity is Severity.BLOCK


def test_r4_inert_when_user_accepted(base_ontology):
    rule = Rule04UserRejectedSynonym()
    cand = Candidate(preferred_label="GI", domain_code="Retail_PI")
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


# ------------------- Rule 5: cross-domain compatible match -------------------

def test_r5_compatible_definition_proposes_skos_match(ontology_with):
    extra = """
bank:CorporateMobileApp
    a skos:Concept ;
    skos:inScheme bank:SchemeProduct ;
    skos:prefLabel "Mobile app"@en ;
    skos:definition "A smartphone application provided by the bank for account management, payments, and product applications."@en .
"""
    onto = ontology_with(extra)
    rule = Rule05CrossDomainCompatibleMatch()
    cand = Candidate(
        preferred_label="Mobile app",
        domain="http://ontobridge.dev/ontology/bank/SchemeProduct",
        definition=(
            "A smartphone application provided by the bank for account management, "
            "payments, and product applications."
        ),
    )
    finding = rule.evaluate(cand, onto)
    assert finding.triggered
    assert finding.severity is Severity.WARN
    assert finding.suggestions["proposed_property"] == "skos:exactMatch"


def test_r5_inert_when_label_unique(base_ontology):
    rule = Rule05CrossDomainCompatibleMatch()
    cand = Candidate(preferred_label="Quantum vault", domain=PI_SCHEME)
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


# ------------------- Rule 6: short uppercase, no context -------------------

def test_r6_blocks_short_uppercase_without_context(base_ontology):
    rule = Rule06UppercaseShortNoContext()
    cand = Candidate(preferred_label="GI")
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered
    assert finding.severity is Severity.BLOCK


def test_r6_passes_when_expansion_provided(base_ontology):
    rule = Rule06UppercaseShortNoContext()
    cand = Candidate(preferred_label="GI", acronym_expansion="Gross income")
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


def test_r6_inert_for_longer_labels(base_ontology):
    rule = Rule06UppercaseShortNoContext()
    cand = Candidate(preferred_label="Customer")
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


# ------------------- Rule 7: single noun without qualifier -------------------

def test_r7_blocks_bare_single_word_no_domain(base_ontology):
    rule = Rule07SingleNounNoQualifier()
    cand = Candidate(preferred_label="Customer")
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered
    assert finding.severity is Severity.BLOCK


def test_r7_passes_when_domain_set(base_ontology):
    rule = Rule07SingleNounNoQualifier()
    cand = Candidate(preferred_label="Customer", domain=PI_SCHEME)
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


def test_r7_passes_for_multi_word(base_ontology):
    rule = Rule07SingleNounNoQualifier()
    cand = Candidate(preferred_label="Retail customer")
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered
