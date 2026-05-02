from __future__ import annotations

from ontobridge.agents.governance.models import Candidate, FIBOMatch, Severity
from ontobridge.agents.governance.rules.conflict import (
    Rule12FIBOMatchDivergent,
    Rule13DeprecatedTermMatch,
    Rule14CrossDomainIncompatibleMatch,
)

PI_SCHEME = "http://ontobridge.dev/ontology/bank/SchemeParty"
PRODUCT_SCHEME = "http://ontobridge.dev/ontology/bank/SchemeProduct"


# ------------------- Rule 12: FIBO definition divergence -------------------

def test_r12_warns_on_divergent_fibo_definition(base_ontology):
    rule = Rule12FIBOMatchDivergent()
    cand = Candidate(
        preferred_label="Customer",
        domain=PI_SCHEME,
        definition="A customer is anyone who walks into a branch on a Sunday.",
        fibo_match=FIBOMatch(
            uri="https://spec.edmcouncil.org/fibo/ontology/FND/Parties/Parties/PartyInRole",
            expected_definition=(
                "A party acting in a particular role with respect to a thing or another "
                "party in a defined context."
            ),
        ),
    )
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered
    assert finding.severity is Severity.WARN
    assert "skos:relatedMatch" in finding.suggestions


def test_r12_passes_when_aligned(base_ontology):
    rule = Rule12FIBOMatchDivergent()
    expected = (
        "A party acting in a particular role with respect to a thing or another "
        "party in a defined context."
    )
    cand = Candidate(
        preferred_label="Customer",
        domain=PI_SCHEME,
        definition=expected,
        fibo_match=FIBOMatch(
            uri="https://spec.edmcouncil.org/fibo/ontology/FND/Parties/Parties/PartyInRole",
            expected_definition=expected,
        ),
    )
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


def test_r12_inert_without_fibo_match(base_ontology):
    rule = Rule12FIBOMatchDivergent()
    cand = Candidate(preferred_label="Customer")
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


# ------------------- Rule 13: deprecated-term match -------------------

def test_r13_warns_on_deprecated_match(ontology_with):
    extra = """
bank:OldRetailCustomer
    a skos:Concept ;
    skos:inScheme bank:SchemeParty ;
    skos:prefLabel "Legacy customer"@en ;
    skos:definition "Deprecated retail customer category superseded by Retail customer."@en ;
    owl:deprecated true .
"""
    onto = ontology_with(extra)
    rule = Rule13DeprecatedTermMatch()
    cand = Candidate(preferred_label="Legacy customer")
    finding = rule.evaluate(cand, onto)
    assert finding.triggered
    assert finding.severity is Severity.WARN
    assert finding.suggestions["require_override"] is True


def test_r13_inert_when_no_deprecated_match(base_ontology):
    rule = Rule13DeprecatedTermMatch()
    cand = Candidate(preferred_label="Retail customer")
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


# ------------------- Rule 14: cross-domain incompatible -------------------

def test_r14_blocks_when_no_qualifier_and_diverging_definition(ontology_with):
    extra = """
bank:CorporateMobileApp
    a skos:Concept ;
    skos:inScheme bank:SchemeProduct ;
    skos:prefLabel "Bridge"@en ;
    skos:definition "A liquidity bridge facility extended between corporate accounts during settlement."@en .
"""
    onto = ontology_with(extra)
    rule = Rule14CrossDomainIncompatibleMatch()
    cand = Candidate(
        preferred_label="Bridge",
        definition="A physical pedestrian crossing maintained by the public works department.",
    )
    finding = rule.evaluate(cand, onto)
    assert finding.triggered
    assert finding.severity is Severity.BLOCK


def test_r14_warns_when_qualifier_present(ontology_with):
    extra = """
bank:CorporateMobileApp
    a skos:Concept ;
    skos:inScheme bank:SchemeProduct ;
    skos:prefLabel "Bridge"@en ;
    skos:definition "A liquidity bridge facility extended between corporate accounts during settlement."@en .
"""
    onto = ontology_with(extra)
    rule = Rule14CrossDomainIncompatibleMatch()
    cand = Candidate(
        preferred_label="Bridge",
        domain=PI_SCHEME,
        domain_code="Retail_PI",
        definition="A physical pedestrian crossing maintained by the public works department.",
    )
    finding = rule.evaluate(cand, onto)
    assert finding.triggered
    assert finding.severity is Severity.WARN


def test_r14_inert_for_compatible_definition(ontology_with):
    extra = """
bank:CorporateMobileApp
    a skos:Concept ;
    skos:inScheme bank:SchemeProduct ;
    skos:prefLabel "Mobile app"@en ;
    skos:definition "A smartphone application provided by the bank for account management, payments, and product applications."@en .
"""
    onto = ontology_with(extra)
    rule = Rule14CrossDomainIncompatibleMatch()
    cand = Candidate(
        preferred_label="Mobile app",
        domain="http://ontobridge.dev/ontology/bank/SchemeChannel",
        definition=(
            "A smartphone application provided by the bank for account management, "
            "payments, and product applications."
        ),
    )
    finding = rule.evaluate(cand, onto)
    assert not finding.triggered
