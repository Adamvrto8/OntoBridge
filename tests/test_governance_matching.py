from __future__ import annotations

from ontobridge.agents.governance.models import Candidate, Severity
from ontobridge.agents.governance.rules.matching import (
    Rule01ExactPrefLabelMatch,
    Rule02AcronymExpansionMatch,
    Rule03FuzzyLabelMatch,
)


# ------------------- Rule 1: exact prefLabel match -------------------

def test_r1_blocks_exact_prefLabel_duplicate(base_ontology):
    rule = Rule01ExactPrefLabelMatch()
    cand = Candidate(preferred_label="Retail customer")  # exists in v0.1 ontology
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered
    assert finding.severity is Severity.BLOCK
    assert "skos:altLabel" in finding.suggestions
    assert finding.suggestions["target_pref_label"] == "Retail customer"


def test_r1_case_insensitive(base_ontology):
    rule = Rule01ExactPrefLabelMatch()
    cand = Candidate(preferred_label="RETAIL CUSTOMER")
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered


def test_r1_passes_for_new_label(base_ontology):
    rule = Rule01ExactPrefLabelMatch()
    cand = Candidate(preferred_label="Frequent flyer status")
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


# ------------------- Rule 2: acronym expansion match -------------------

def test_r2_acronym_expansion_explicit(base_ontology):
    rule = Rule02AcronymExpansionMatch()
    cand = Candidate(preferred_label="UWP", acronym_expansion="Underwriting profile")
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered
    assert finding.suggestions["match_kind"] == "explicit_expansion"


def test_r2_acronym_initials_match(base_ontology):
    # "RC" should match "Retail customer" via initials.
    rule = Rule02AcronymExpansionMatch()
    cand = Candidate(preferred_label="RC")
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered
    assert finding.suggestions["match_kind"] == "derived_initials"


def test_r2_passes_when_no_match(base_ontology):
    rule = Rule02AcronymExpansionMatch()
    cand = Candidate(preferred_label="ZZQ")
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


# ------------------- Rule 3: fuzzy label match -------------------

def test_r3_warns_on_high_similarity(base_ontology):
    rule = Rule03FuzzyLabelMatch()
    # "Retail custmer" (typo) should fuzzy-match "Retail customer"
    cand = Candidate(preferred_label="Retail custmer")
    finding = rule.evaluate(cand, base_ontology)
    assert finding.triggered
    assert finding.severity is Severity.WARN
    top = finding.suggestions["candidates"][0]
    assert top["label"].lower() == "retail customer"
    assert top["score"] >= 0.80


def test_r3_passes_for_clearly_different_label(base_ontology):
    rule = Rule03FuzzyLabelMatch()
    cand = Candidate(preferred_label="Telegraph operator licence")
    finding = rule.evaluate(cand, base_ontology)
    assert not finding.triggered


def test_r3_excludes_the_exact_match_itself(base_ontology):
    # Rule 3 only flags 0.80 <= s < 1.0; the exact match (score 1.0) is rule 1's job.
    # Other near-matches in the ontology may still surface — that's expected.
    rule = Rule03FuzzyLabelMatch()
    cand = Candidate(preferred_label="Retail customer")
    finding = rule.evaluate(cand, base_ontology)
    suggested_labels = {s["label"] for s in finding.suggestions.get("candidates", [])}
    assert "Retail customer" not in suggested_labels
