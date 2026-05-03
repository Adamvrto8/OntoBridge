from __future__ import annotations

from collections import Counter

import pytest

from ontobridge.dashboard.config import DashboardConfig
from ontobridge.dashboard.seed import (
    SampleTermSpec,
    build_sample_publisher,
    sample_term_specs,
)
from ontobridge.models import LifecycleStatus
from ontobridge.publisher import InMemoryPublisher


def test_sample_specs_match_pipeline_input_contract():
    specs = sample_term_specs()
    assert 5 <= len(specs) <= 8
    for spec in specs:
        # PipelineRunner requires both label and definition (NER + Definition skipped).
        assert spec.label and spec.label.strip()
        assert spec.definition and len(spec.definition.split()) >= 10


def test_build_sample_publisher_returns_in_memory(base_ontology):
    pub = build_sample_publisher(base_ontology)
    assert isinstance(pub, InMemoryPublisher)
    terms = pub.search_terms("")
    assert 5 <= len(terms) <= 8


def test_seed_covers_multiple_lifecycle_states(base_ontology):
    pub = build_sample_publisher(base_ontology)
    terms = pub.search_terms("")
    statuses = Counter(t.lifecycle_status for t in terms)
    # The dashboard needs at least three distinct states populated to make the
    # inbox filter meaningful (CANDIDATE for blocked terms, REVIEW for the
    # default queue, PUBLISHED for the glossary).
    assert len(set(statuses)) >= 3
    assert statuses[LifecycleStatus.PUBLISHED] >= 1
    assert statuses[LifecycleStatus.CANDIDATE] >= 1


def test_seed_includes_at_least_one_governance_blocked_term(base_ontology):
    pub = build_sample_publisher(base_ontology)
    blocked = [
        t
        for t in pub.search_terms("")
        if t.enriched_term.governance_result
        and t.enriched_term.governance_result.recommended_action == "block"
    ]
    assert blocked, "expected at least one term blocked by governance"


def test_seed_terms_have_turtle_attached(base_ontology):
    pub = build_sample_publisher(base_ontology)
    for term in pub.search_terms(""):
        assert term.turtle, f"missing Turtle for {term.term_uri}"
        assert "skos:prefLabel" in term.turtle


def test_seed_is_idempotent_per_call(base_ontology):
    pub_a = build_sample_publisher(base_ontology)
    pub_b = build_sample_publisher(base_ontology)
    uris_a = {t.term_uri for t in pub_a.search_terms("")}
    uris_b = {t.term_uri for t in pub_b.search_terms("")}
    assert uris_a == uris_b


def test_seed_with_custom_specs(base_ontology):
    custom = [
        SampleTermSpec(
            label="Dashboard custom term",
            definition=(
                "A test term with enough words in its definition to satisfy the "
                "governance rule about minimum definition length."
            ),
            policy_document="TestPolicy.pdf",
            policy_section="1.0",
            approved_by="alice",
        ),
    ]
    pub = build_sample_publisher(base_ontology, specs=custom)
    terms = pub.search_terms("")
    assert len(terms) == 1
    assert terms[0].enriched_term.preferred_label == "Dashboard custom term"


def test_default_dashboard_config_points_at_v0_1_ontology():
    cfg = DashboardConfig()
    assert cfg.ontology_path.exists(), (
        f"DashboardConfig.ontology_path does not resolve to a real file: "
        f"{cfg.ontology_path}"
    )
    assert cfg.ontology_path.name == "ontobridge_ontology_v0.1.ttl"
    assert cfg.miro_board_url is None  # placeholder by default
