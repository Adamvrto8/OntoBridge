from __future__ import annotations

import pytest

from ontobridge.dashboard.views.graph import _scheme_color, build_graph_data
from ontobridge.models import LifecycleStatus
from ontobridge.models.enrichment import (
    CandidateLabel,
    EnrichedTerm,
    SemanticRelation,
    TaxonomyPlacement,
)
from ontobridge.models.enums import PlacementStatus, RelationStatus
from ontobridge.models.enums import SourceType
from ontobridge.models.published import PublishedTerm
from ontobridge.models.source import HarvestRecord, SourceRef

_SCHEME = "http://ontobridge.dev/ontology/bank/LoanScheme"
_NS = "http://ontobridge.dev/ontology/bank/"


def _make_term(
    uri: str,
    label: str,
    *,
    parent_uri: str | None = None,
    scheme_uri: str | None = None,
    definition: str | None = None,
) -> PublishedTerm:
    record = HarvestRecord(
        text=f"{label} is a banking term.",
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="test", document_id="doc1"),
    )
    enriched = EnrichedTerm(
        harvest_record=record,
        candidate_labels=[CandidateLabel(text=label, confidence=1.0)],
        definition=definition,
    )
    if parent_uri:
        enriched.taxonomy_placement = TaxonomyPlacement(
            broader_concept_uri=parent_uri,
            scheme_uri=scheme_uri or _SCHEME,
            status=PlacementStatus.PLACED,
        )
    return PublishedTerm(
        enriched_term=enriched,
        term_uri=uri,
        lifecycle_status=LifecycleStatus.PUBLISHED,
        approved_by="alice",
    )


def _make_relation(subject_uri: str, verb: str, object_label: str) -> SemanticRelation:
    return SemanticRelation(
        subject_uri=subject_uri,
        predicate_uri=f"{_NS}{verb}",
        object_label=object_label,
        inverse_predicate_uri=f"{_NS}inverse_{verb}",
        verb=verb,
        confidence=0.9,
        status=RelationStatus.RESOLVED,
    )


# ---------------------------------------------------------------------------
# _scheme_color
# ---------------------------------------------------------------------------

def test_scheme_color_known_scheme():
    assert _scheme_color("http://ontobridge.dev/ontology/bank/LoanScheme") == "#4a90d9"


def test_scheme_color_unknown_scheme():
    assert _scheme_color("http://example.com/UnknownScheme") == "#7f8c8d"


def test_scheme_color_none():
    assert _scheme_color(None) == "#7f8c8d"


# ---------------------------------------------------------------------------
# build_graph_data — nodes
# ---------------------------------------------------------------------------

def test_empty_list_returns_empty():
    nodes, edges = build_graph_data([])
    assert nodes == []
    assert edges == []


def test_single_term_produces_one_node_no_edges():
    term = _make_term(f"{_NS}Mortgage", "Mortgage")
    nodes, edges = build_graph_data([term])
    assert len(nodes) == 1
    assert nodes[0]["label"] == "Mortgage"
    assert nodes[0]["id"] == f"{_NS}Mortgage"
    assert edges == []


def test_node_tooltip_includes_definition():
    term = _make_term(f"{_NS}LTV", "LTV", definition="Loan-to-value ratio used in lending.")
    nodes, _ = build_graph_data([term])
    assert "Loan-to-value" in nodes[0]["title"]


def test_node_color_reflects_scheme():
    term = _make_term(
        f"{_NS}Mortgage", "Mortgage",
        parent_uri=f"{_NS}Loan",
        scheme_uri=_SCHEME,
    )
    # Need a parent in the list for taxonomy edge — but color is set regardless
    nodes, _ = build_graph_data([term])
    assert nodes[0]["color"] == "#4a90d9"


# ---------------------------------------------------------------------------
# build_graph_data — taxonomy edges
# ---------------------------------------------------------------------------

def test_taxonomy_edge_when_parent_in_list():
    parent = _make_term(f"{_NS}Loan", "Loan")
    child = _make_term(f"{_NS}Mortgage", "Mortgage", parent_uri=f"{_NS}Loan")
    nodes, edges = build_graph_data([parent, child])
    assert len(nodes) == 2
    taxonomy_edges = [e for e in edges if e["label"] == "broader"]
    assert len(taxonomy_edges) == 1
    assert taxonomy_edges[0]["source"] == f"{_NS}Loan"
    assert taxonomy_edges[0]["target"] == f"{_NS}Mortgage"


def test_no_taxonomy_edge_when_parent_not_in_list():
    child = _make_term(f"{_NS}Mortgage", "Mortgage", parent_uri=f"{_NS}ExternalConcept")
    _, edges = build_graph_data([child])
    assert edges == []


# ---------------------------------------------------------------------------
# build_graph_data — semantic relation edges
# ---------------------------------------------------------------------------

def test_semantic_relation_edge_when_object_label_matches():
    ltv = _make_term(f"{_NS}LTV", "LTV")
    mortgage = _make_term(f"{_NS}Mortgage", "Mortgage")
    ltv.enriched_term.relations.append(
        _make_relation(f"{_NS}LTV", "governs", "Mortgage")
    )
    _, edges = build_graph_data([ltv, mortgage])
    rel_edges = [e for e in edges if e["label"] == "governs"]
    assert len(rel_edges) == 1
    assert rel_edges[0]["source"] == f"{_NS}LTV"
    assert rel_edges[0]["target"] == f"{_NS}Mortgage"


def test_no_relation_edge_when_object_label_unknown():
    ltv = _make_term(f"{_NS}LTV", "LTV")
    ltv.enriched_term.relations.append(
        _make_relation(f"{_NS}LTV", "governs", "UnknownTerm")
    )
    _, edges = build_graph_data([ltv])
    assert edges == []


def test_self_loop_is_skipped():
    term = _make_term(f"{_NS}LTV", "LTV")
    term.enriched_term.relations.append(
        _make_relation(f"{_NS}LTV", "governs", "LTV")
    )
    _, edges = build_graph_data([term])
    assert edges == []


def test_duplicate_edges_are_deduplicated():
    ltv = _make_term(f"{_NS}LTV", "LTV")
    mortgage = _make_term(f"{_NS}Mortgage", "Mortgage")
    rel = _make_relation(f"{_NS}LTV", "governs", "Mortgage")
    ltv.enriched_term.relations.extend([rel, rel])
    _, edges = build_graph_data([ltv, mortgage])
    governs_edges = [e for e in edges if e["label"] == "governs"]
    assert len(governs_edges) == 1


def test_case_insensitive_object_label_match():
    ltv = _make_term(f"{_NS}LTV", "LTV")
    mortgage = _make_term(f"{_NS}Mortgage", "Mortgage")
    ltv.enriched_term.relations.append(
        _make_relation(f"{_NS}LTV", "governs", "MORTGAGE")
    )
    _, edges = build_graph_data([ltv, mortgage])
    assert any(e["label"] == "governs" for e in edges)
