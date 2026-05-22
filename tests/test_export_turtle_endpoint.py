"""Integration tests for GET /api/terms/export/turtle."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from rdflib import Graph

from ontobridge.api.main import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory, base_ontology):
    tmp_path = tmp_path_factory.mktemp("export")
    app = create_app(ontology_path=str(tmp_path / "onto.ttl"))
    import ontobridge.dashboard.seed as seed_mod
    _orig_load = seed_mod.load_ontology
    _orig_build = seed_mod.build_sample_publisher
    seed_mod.load_ontology = lambda _: base_ontology
    seed_mod.build_sample_publisher = lambda ont, **kw: _orig_build(base_ontology)
    with TestClient(app) as c:
        yield c
    seed_mod.load_ontology = _orig_load
    seed_mod.build_sample_publisher = _orig_build


# ---------------------------------------------------------------------------
# Content type and headers
# ---------------------------------------------------------------------------

def test_returns_turtle_content_type(client):
    res = client.get("/api/terms/export/turtle")
    assert res.status_code == 200
    assert "text/turtle" in res.headers["content-type"]


def test_returns_attachment_header(client):
    res = client.get("/api/terms/export/turtle")
    assert "attachment" in res.headers.get("content-disposition", "")
    assert ".ttl" in res.headers.get("content-disposition", "")


# ---------------------------------------------------------------------------
# Valid Turtle output
# ---------------------------------------------------------------------------

def test_response_is_parseable_turtle(client):
    res = client.get("/api/terms/export/turtle")
    g = Graph()
    g.parse(data=res.text, format="turtle")
    assert len(g) > 0


def test_export_contains_skos_concepts(client):
    from rdflib.namespace import SKOS
    res = client.get("/api/terms/export/turtle")
    g = Graph()
    g.parse(data=res.text, format="turtle")
    concepts = list(g.subjects(predicate=None, object=SKOS.Concept))
    assert len(concepts) > 0


def test_export_contains_pref_labels(client):
    from rdflib.namespace import SKOS
    res = client.get("/api/terms/export/turtle")
    g = Graph()
    g.parse(data=res.text, format="turtle")
    labels = list(g.objects(predicate=SKOS.prefLabel))
    assert len(labels) > 0


# ---------------------------------------------------------------------------
# Status filter
# ---------------------------------------------------------------------------

def test_status_all_includes_non_published(client):
    default_res = client.get("/api/terms/export/turtle")
    all_res = client.get("/api/terms/export/turtle?status=all")
    g_default = Graph()
    g_default.parse(data=default_res.text, format="turtle")
    g_all = Graph()
    g_all.parse(data=all_res.text, format="turtle")
    # all statuses should have at least as many triples as published-only
    assert len(g_all) >= len(g_default)


def test_unknown_status_falls_back_to_published(client):
    res = client.get("/api/terms/export/turtle?status=nonexistent")
    assert res.status_code == 200
    assert "text/turtle" in res.headers["content-type"]
