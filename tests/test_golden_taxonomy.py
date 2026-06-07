"""
Golden dataset tests for TaxonomyAgent.

Ground truth: skos:broader triples from the ontology itself.
For each golden pair (child → expected_parent) we strip the child's
position from context, run TaxonomyAgent on its label + definition,
and assert it returns the correct broader concept URI.

These tests are deterministic, require no API key, and run in < 1 s.
"""

from __future__ import annotations

import pytest
from rdflib.namespace import SKOS

from ontobridge.agents.taxonomy import TaxonomyAgent
from ontobridge.models.enrichment import CandidateLabel, EnrichedTerm
from ontobridge.models.enums import PlacementStatus
from ontobridge.models.source import HarvestRecord, SourceRef, SourceType, Tier


# ─── Golden pairs ─────────────────────────────────────────────────────────────
#
# Format: (child_label, expected_parent_label)
# Chosen to be unambiguous — any banking expert would agree on the parent.
# Each pair is verified against skos:broader in the ontology (see fixture below).

GOLDEN_PAIRS = [
    ("Corporate customer",   "Customer"),
    ("Retail customer",      "Customer"),
    ("Credit card",          "Credit product"),
    ("Consumer loan",        "Credit product"),
    ("Credit product",       "Financial product"),
    ("Branch",               "Channel"),
    ("ATM",                  "Channel"),
    ("Application form",     "Document"),
    ("Contract",             "Document"),
    ("Basel Accord",         "Regulation"),
    ("Committee",            "Organisational unit"),
    ("Department",           "Organisational unit"),
    ("Core banking system",  "Information system"),
    ("Annual percentage rate", "Interest rate"),
]


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _build_label_to_uri(ontology) -> dict[str, str]:
    """Map pref_label → URI for all concepts in the ontology."""
    return {c.pref_label: c.uri for c in ontology.concepts}


def _build_broader_map(ontology) -> dict[str, str]:
    """Map child_uri → parent_uri from skos:broader triples in the graph."""
    return {
        str(child): str(parent)
        for child, parent in ontology.graph.subject_objects(SKOS.broader)
    }


def _make_term(label: str, definition: str) -> EnrichedTerm:
    record = HarvestRecord(
        text=definition,
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="golden"),
        tier=Tier.UNSTRUCTURED,
    )
    t = EnrichedTerm.from_harvest(record)
    t.candidate_labels = [CandidateLabel(text=label, confidence=0.95)]
    t.definition = definition
    return t


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def label_to_uri(base_ontology) -> dict[str, str]:
    return _build_label_to_uri(base_ontology)


@pytest.fixture(scope="module")
def broader_map(base_ontology) -> dict[str, str]:
    return _build_broader_map(base_ontology)


@pytest.fixture(scope="module")
def tax_agent(base_ontology) -> TaxonomyAgent:
    return TaxonomyAgent(base_ontology)


# ─── Sanity check: golden pairs exist in ontology ────────────────────────────


def test_all_golden_pairs_exist_in_ontology(base_ontology, label_to_uri, broader_map):
    """Verify every golden pair is actually in the ontology before trusting it."""
    missing = []
    wrong_parent = []

    for child_label, expected_parent_label in GOLDEN_PAIRS:
        child_uri = label_to_uri.get(child_label)
        parent_uri = label_to_uri.get(expected_parent_label)

        if not child_uri:
            missing.append(f"child not found: '{child_label}'")
            continue
        if not parent_uri:
            missing.append(f"parent not found: '{expected_parent_label}'")
            continue
        if broader_map.get(child_uri) != parent_uri:
            actual = broader_map.get(child_uri, "(none)")
            actual_label = next(
                (c.pref_label for c in base_ontology.concepts if c.uri == actual), actual
            )
            wrong_parent.append(
                f"'{child_label}' → expected '{expected_parent_label}', "
                f"ontology says '{actual_label}'"
            )

    errors = missing + wrong_parent
    assert not errors, "Golden pairs have errors:\n" + "\n".join(errors)


# ─── Core golden dataset test ─────────────────────────────────────────────────


def _definition_for(label: str, base_ontology) -> str:
    for c in base_ontology.concepts:
        if c.pref_label == label and c.definition:
            return c.definition
    pytest.skip(f"No definition found in ontology for '{label}'")


@pytest.mark.parametrize("child_label,expected_parent_label", GOLDEN_PAIRS)
def test_taxonomy_agent_finds_correct_parent(
    child_label,
    expected_parent_label,
    base_ontology,
    tax_agent,
    label_to_uri,
):
    definition = _definition_for(child_label, base_ontology)
    expected_parent_uri = label_to_uri[expected_parent_label]

    term = _make_term(child_label, definition)
    tax_agent.apply(term)
    placement = term.taxonomy_placement

    assert placement.status == PlacementStatus.PLACED, (
        f"TaxonomyAgent returned UNRESOLVED for '{child_label}' "
        f"(expected parent: '{expected_parent_label}')"
    )

    actual_label = next(
        (c.pref_label for c in base_ontology.concepts if c.uri == placement.broader_concept_uri),
        placement.broader_concept_uri,
    )

    assert placement.broader_concept_uri == expected_parent_uri, (
        f"'{child_label}': expected parent '{expected_parent_label}', "
        f"TaxonomyAgent returned '{actual_label}'"
    )


# ─── Accuracy summary ─────────────────────────────────────────────────────────


def test_taxonomy_accuracy_at_least_80_percent(base_ontology, tax_agent, label_to_uri):
    """
    Soft threshold: TaxonomyAgent must correctly place at least 80% of the
    golden pairs.  Failing individual cases above is the primary signal;
    this test catches global regression (e.g. after threshold tuning).
    """
    correct = 0
    total = len(GOLDEN_PAIRS)
    failures = []

    for child_label, expected_parent_label in GOLDEN_PAIRS:
        definition = next(
            (c.definition for c in base_ontology.concepts if c.pref_label == child_label),
            None,
        )
        if not definition:
            total -= 1
            continue

        expected_uri = label_to_uri.get(expected_parent_label)
        if not expected_uri:
            total -= 1
            continue

        t = _make_term(child_label, definition)
        tax_agent.apply(t)
        placement = t.taxonomy_placement
        if placement.broader_concept_uri == expected_uri:
            correct += 1
        else:
            actual_label = next(
                (c.pref_label for c in base_ontology.concepts
                 if c.uri == placement.broader_concept_uri),
                placement.broader_concept_uri,
            )
            failures.append(f"  WRONG: '{child_label}' → '{actual_label}' (expected '{expected_parent_label}')")

    accuracy = correct / total if total > 0 else 0.0
    summary = f"Accuracy: {correct}/{total} = {accuracy:.0%}"
    if failures:
        summary += "\nFailures:\n" + "\n".join(failures)

    assert accuracy >= 0.80, summary
