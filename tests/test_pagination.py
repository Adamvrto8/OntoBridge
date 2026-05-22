"""Tests for paginated list endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ontobridge.api.main import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory, base_ontology):
    tmp_path = tmp_path_factory.mktemp("pagination")
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
# GET /api/terms — PagedResponse envelope
# ---------------------------------------------------------------------------

def test_terms_returns_paged_envelope(client):
    res = client.get("/api/terms")
    assert res.status_code == 200
    body = res.json()
    assert "items" in body
    assert "total" in body
    assert "limit" in body
    assert "offset" in body


def test_terms_items_is_list(client):
    body = client.get("/api/terms").json()
    assert isinstance(body["items"], list)


def test_terms_total_matches_items_without_pagination(client):
    body = client.get("/api/terms?limit=500").json()
    assert body["total"] == len(body["items"])


def test_terms_limit_param_respected(client):
    full = client.get("/api/terms?limit=500").json()
    if full["total"] < 2:
        pytest.skip("need at least 2 terms")
    page1 = client.get("/api/terms?limit=1&offset=0").json()
    assert len(page1["items"]) == 1
    assert page1["limit"] == 1
    assert page1["offset"] == 0
    assert page1["total"] == full["total"]


def test_terms_offset_advances_page(client):
    full = client.get("/api/terms?limit=500").json()
    if full["total"] < 2:
        pytest.skip("need at least 2 terms")
    p1 = client.get("/api/terms?limit=1&offset=0").json()["items"]
    p2 = client.get("/api/terms?limit=1&offset=1").json()["items"]
    assert p1[0]["term_uri"] != p2[0]["term_uri"]


def test_terms_offset_beyond_total_returns_empty_items(client):
    body = client.get("/api/terms?offset=99999").json()
    assert body["items"] == []
    assert body["total"] >= 0


def test_terms_limit_capped_at_max(client):
    body = client.get("/api/terms?limit=99999").json()
    assert body["limit"] == 500


def test_terms_negative_offset_treated_as_zero(client):
    body = client.get("/api/terms?offset=-5").json()
    assert body["offset"] == 0


# ---------------------------------------------------------------------------
# GET /api/audit — PagedResponse envelope
# ---------------------------------------------------------------------------

def test_audit_returns_paged_envelope(client):
    res = client.get("/api/audit")
    assert res.status_code == 200
    body = res.json()
    assert "items" in body
    assert "total" in body
    assert "limit" in body
    assert "offset" in body


def test_audit_limit_param_respected(client):
    body = client.get("/api/audit?limit=1").json()
    assert len(body["items"]) <= 1
    assert body["limit"] == 1


def test_audit_limit_capped_at_max(client):
    body = client.get("/api/audit?limit=99999").json()
    assert body["limit"] == 500
