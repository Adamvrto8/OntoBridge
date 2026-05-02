from __future__ import annotations

from ontobridge.agents.governance.models import Candidate, PolicyRef, Severity
from ontobridge.agents.governance.rules.quality import (
    Rule08DefinitionTooShort,
    Rule09CircularDefinition,
    Rule10NoPolicySource,
    Rule11MultiPolicySource,
)


# ------------------- Rule 8: definition < 10 words -------------------

def test_r8_blocks_short_definition(base_ontology):
    rule = Rule08DefinitionTooShort()
    cand = Candidate(preferred_label="Foo", definition="A short five word definition.")
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered
    assert finding.severity is Severity.BLOCK
    assert finding.suggestions["block_publish"] is True


def test_r8_passes_for_full_definition(base_ontology):
    rule = Rule08DefinitionTooShort()
    cand = Candidate(
        preferred_label="Foo",
        definition=(
            "A retail bank customer in the Personal Instalment segment who holds "
            "instalment-based credit products with the bank."
        ),
    )
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


# ------------------- Rule 9: circular definition -------------------

def test_r9_blocks_circular_definition(base_ontology):
    rule = Rule09CircularDefinition()
    cand = Candidate(
        preferred_label="Mobile app",
        definition="A mobile app provided by the bank for account management.",
    )
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered
    assert finding.severity is Severity.BLOCK


def test_r9_passes_for_non_circular(base_ontology):
    rule = Rule09CircularDefinition()
    cand = Candidate(
        preferred_label="Mobile app",
        definition="A smartphone application for accessing banking services.",
    )
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


# ------------------- Rule 10: no policy source -------------------

def test_r10_blocks_when_no_policy_refs(base_ontology):
    rule = Rule10NoPolicySource()
    cand = Candidate(preferred_label="Foo")
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered
    assert finding.severity is Severity.BLOCK
    assert finding.suggestions["provenance_status"] == "awaiting source"


def test_r10_passes_when_policy_refs_present(base_ontology):
    rule = Rule10NoPolicySource()
    cand = Candidate(
        preferred_label="Foo",
        policy_refs=[PolicyRef(document="CreditPolicy_v3.pdf", section="2.1")],
    )
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


# ------------------- Rule 11: multi-policy source -------------------

def test_r11_warns_when_multiple_documents(base_ontology):
    rule = Rule11MultiPolicySource()
    cand = Candidate(
        preferred_label="Foo",
        policy_refs=[
            PolicyRef(document="CreditPolicy_v3.pdf"),
            PolicyRef(document="OnboardingPolicy_v2.pdf"),
        ],
    )
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered
    assert finding.severity is Severity.WARN
    assert finding.suggestions["require_steward_signoff"] is True


def test_r11_inert_for_single_document(base_ontology):
    rule = Rule11MultiPolicySource()
    cand = Candidate(
        preferred_label="Foo",
        policy_refs=[
            PolicyRef(document="CreditPolicy_v3.pdf", section="2.1"),
            PolicyRef(document="CreditPolicy_v3.pdf", section="2.2"),
        ],
    )
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered
