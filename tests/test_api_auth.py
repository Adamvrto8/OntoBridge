"""Tests for API key authentication middleware."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from ontobridge.api.main import create_app


@pytest.fixture()
def client(tmp_path, base_ontology, monkeypatch):
    """TestClient with auth disabled (no ONTOBRIDGE_API_KEY set)."""
    monkeypatch.delenv("ONTOBRIDGE_API_KEY", raising=False)
    app = create_app(ontology_path=str(tmp_path / "onto.ttl"))
    # Patch ontology load so we don't need a real file
    import ontobridge.dashboard.seed as seed_mod
    monkeypatch.setattr(seed_mod, "load_ontology", lambda _: base_ontology)
    monkeypatch.setattr(seed_mod, "build_sample_publisher", lambda ont, **kw: _empty_publisher())
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def authed_client(tmp_path, base_ontology, monkeypatch):
    """TestClient with ONTOBRIDGE_API_KEY=test-secret-key."""
    monkeypatch.setenv("ONTOBRIDGE_API_KEY", "test-secret-key")
    app = create_app(ontology_path=str(tmp_path / "onto.ttl"))
    import ontobridge.dashboard.seed as seed_mod
    monkeypatch.setattr(seed_mod, "load_ontology", lambda _: base_ontology)
    monkeypatch.setattr(seed_mod, "build_sample_publisher", lambda ont, **kw: _empty_publisher())
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _empty_publisher():
    from ontobridge.publisher import InMemoryPublisher
    return InMemoryPublisher()


# ---------------------------------------------------------------------------
# Auth disabled (no env var)
# ---------------------------------------------------------------------------

def test_no_key_required_when_env_not_set(client):
    res = client.get("/api/stats")
    assert res.status_code == 200


def test_key_still_accepted_when_auth_disabled(client):
    res = client.get("/api/stats", headers={"X-API-Key": "anything"})
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Auth enabled (env var set)
# ---------------------------------------------------------------------------

def test_missing_key_returns_401(authed_client):
    res = authed_client.get("/api/stats")
    assert res.status_code == 401


def test_wrong_key_returns_401(authed_client):
    res = authed_client.get("/api/stats", headers={"X-API-Key": "wrong-key"})
    assert res.status_code == 401


def test_correct_key_returns_200(authed_client):
    res = authed_client.get("/api/stats", headers={"X-API-Key": "test-secret-key"})
    assert res.status_code == 200


def test_401_body_has_detail(authed_client):
    res = authed_client.get("/api/stats")
    assert "detail" in res.json()


def test_auth_applies_to_post_routes_too(authed_client):
    res = authed_client.post("/api/pipeline/run")
    # 401 before any body validation
    assert res.status_code == 401


def test_auth_applies_to_patch_routes_too(authed_client):
    res = authed_client.patch("/api/terms/some-uri/status", json={})
    assert res.status_code == 401
