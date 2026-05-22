"""Tests for the outbound webhook module."""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from ontobridge import webhook


# ---------------------------------------------------------------------------
# Unit tests — webhook.fire()
# ---------------------------------------------------------------------------

def test_no_op_when_url_not_set(monkeypatch):
    monkeypatch.delenv("ONTOBRIDGE_WEBHOOK_URL", raising=False)
    with patch("ontobridge.webhook._send") as mock_send:
        webhook.fire("term.published", "http://x/Term", "Term", "published")
    mock_send.assert_not_called()


def test_fires_when_url_set(monkeypatch):
    monkeypatch.setenv("ONTOBRIDGE_WEBHOOK_URL", "http://example.com/hook")
    monkeypatch.delenv("ONTOBRIDGE_WEBHOOK_SECRET", raising=False)
    sent: list[dict] = []

    def fake_send(url, payload, secret):
        sent.append(payload)

    with patch("ontobridge.webhook._send", side_effect=fake_send):
        webhook.fire("term.published", "http://x/Mortgage", "Mortgage", "published",
                     definition="A loan secured by property.")
        # give background thread time to run
        time.sleep(0.05)

    assert len(sent) == 1
    assert sent[0]["event"] == "term.published"
    assert sent[0]["term"]["label"] == "Mortgage"
    assert sent[0]["term"]["status"] == "published"
    assert sent[0]["term"]["definition"] == "A loan secured by property."


def test_payload_contains_timestamp(monkeypatch):
    monkeypatch.setenv("ONTOBRIDGE_WEBHOOK_URL", "http://example.com/hook")
    sent: list[dict] = []

    def fake_send(url, payload, secret):
        sent.append(payload)

    with patch("ontobridge.webhook._send", side_effect=fake_send):
        webhook.fire("term.status_changed", "http://x/KYC", "KYC", "review")
        time.sleep(0.05)

    assert "timestamp" in sent[0]
    assert "T" in sent[0]["timestamp"]  # ISO 8601


def test_all_term_fields_present(monkeypatch):
    monkeypatch.setenv("ONTOBRIDGE_WEBHOOK_URL", "http://example.com/hook")
    sent: list[dict] = []

    def fake_send(url, payload, secret):
        sent.append(payload)

    with patch("ontobridge.webhook._send", side_effect=fake_send):
        webhook.fire(
            event="term.published",
            term_uri="http://x/AML",
            term_label="AML",
            new_status="published",
            definition="Anti-money laundering process.",
            scheme="Compliance",
            approved_by="alice",
            alt_labels=["Anti-Money Laundering"],
            fibo_uri="https://spec.edmcouncil.org/fibo/AML",
        )
        time.sleep(0.05)

    term = sent[0]["term"]
    assert term["uri"] == "http://x/AML"
    assert term["scheme"] == "Compliance"
    assert term["approved_by"] == "alice"
    assert "Anti-Money Laundering" in term["alt_labels"]
    assert term["fibo_uri"] == "https://spec.edmcouncil.org/fibo/AML"


# ---------------------------------------------------------------------------
# HMAC signing
# ---------------------------------------------------------------------------

def test_signature_header_added_when_secret_set(monkeypatch):
    monkeypatch.setenv("ONTOBRIDGE_WEBHOOK_URL", "http://example.com/hook")
    monkeypatch.setenv("ONTOBRIDGE_WEBHOOK_SECRET", "mysecret")
    captured: list[dict] = []

    def fake_post(url, *, content, headers, **kw):
        captured.append({"body": content, "headers": headers})
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.status_code = 200
        return resp

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = lambda s: mock_client
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = fake_post

        webhook.fire("term.published", "http://x/T", "T", "published")
        time.sleep(0.1)

    assert mock_client.post.called
    _, kwargs = mock_client.post.call_args
    sig_header = kwargs["headers"].get("X-OntoBridge-Signature", "")
    assert sig_header.startswith("sha256=")

    # Verify the HMAC is correct
    body_bytes = kwargs["content"]
    expected = "sha256=" + hmac.new(b"mysecret", body_bytes, hashlib.sha256).hexdigest()
    assert sig_header == expected


def test_no_signature_header_without_secret(monkeypatch):
    monkeypatch.setenv("ONTOBRIDGE_WEBHOOK_URL", "http://example.com/hook")
    monkeypatch.delenv("ONTOBRIDGE_WEBHOOK_SECRET", raising=False)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = lambda s: mock_client
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        mock_client.post.return_value = resp

        webhook.fire("term.published", "http://x/T", "T", "published")
        time.sleep(0.1)

    _, kwargs = mock_client.post.call_args
    assert "X-OntoBridge-Signature" not in kwargs["headers"]


# ---------------------------------------------------------------------------
# Failure resilience
# ---------------------------------------------------------------------------

def test_delivery_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv("ONTOBRIDGE_WEBHOOK_URL", "http://unreachable.invalid/hook")

    # Should not raise even when httpx fails
    webhook.fire("term.published", "http://x/T", "T", "published")
    time.sleep(0.1)  # let background thread finish


def test_fire_is_non_blocking(monkeypatch):
    monkeypatch.setenv("ONTOBRIDGE_WEBHOOK_URL", "http://example.com/hook")

    def slow_send(url, payload, secret):
        time.sleep(2)

    with patch("ontobridge.webhook._send", side_effect=slow_send):
        start = time.monotonic()
        webhook.fire("term.published", "http://x/T", "T", "published")
        elapsed = time.monotonic() - start

    assert elapsed < 0.5, "fire() should return immediately, not wait for delivery"
