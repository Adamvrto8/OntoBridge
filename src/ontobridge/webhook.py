"""Outbound webhook — notifies downstream systems when a term's status changes.

Configuration (env vars):
    ONTOBRIDGE_WEBHOOK_URL     Target URL for POST requests. Required to enable.
    ONTOBRIDGE_WEBHOOK_SECRET  Optional HMAC-SHA256 signing secret. When set,
                               every request carries an X-OntoBridge-Signature
                               header so the recipient can verify the payload.

Payload format:
    {
        "event":     "term.published" | "term.status_changed",
        "timestamp": "2026-05-22T10:30:00Z",
        "term": {
            "uri":         "http://ontobridge.dev/ontology/bank/Mortgage",
            "label":       "Mortgage",
            "status":      "published",
            "definition":  "A loan secured by real property...",
            "scheme":      "Product",
            "approved_by": "alice",
            "alt_labels":  ["Home Loan"],
            "fibo_uri":    "https://spec.edmcouncil.org/fibo/..."
        }
    }

Delivery is fire-and-forget (background thread). Failures are logged but
never raise exceptions — the API response is never blocked by webhook delivery.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _webhook_url() -> str:
    return os.environ.get("ONTOBRIDGE_WEBHOOK_URL", "").strip()


def _webhook_secret() -> str:
    return os.environ.get("ONTOBRIDGE_WEBHOOK_SECRET", "").strip()


def _sign(payload_bytes: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def _send(url: str, payload: dict, secret: str) -> None:
    try:
        import httpx
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "OntoBridge-Webhook/1.0",
        }
        if secret:
            headers["X-OntoBridge-Signature"] = _sign(body, secret)

        with httpx.Client(timeout=10) as client:
            r = client.post(url, content=body, headers=headers)
            r.raise_for_status()
            logger.info("Webhook delivered: %s %s → %s", payload["event"], payload["term"]["uri"], r.status_code)
    except Exception as exc:
        logger.warning("Webhook delivery failed (%s): %s", url, exc)


def fire(event: str, term_uri: str, term_label: str, new_status: str,
         definition: str | None = None, scheme: str | None = None,
         approved_by: str | None = None, alt_labels: list[str] | None = None,
         fibo_uri: str | None = None) -> None:
    """Send a webhook in a background thread.

    No-op when ONTOBRIDGE_WEBHOOK_URL is not set.
    Never raises — failures are logged only.
    """
    url = _webhook_url()
    if not url:
        return

    payload: dict = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "term": {
            "uri": term_uri,
            "label": term_label,
            "status": new_status,
            "definition": definition or "",
            "scheme": scheme or "",
            "approved_by": approved_by or "",
            "alt_labels": alt_labels or [],
            "fibo_uri": fibo_uri or "",
        },
    }

    secret = _webhook_secret()
    thread = threading.Thread(target=_send, args=(url, payload, secret), daemon=True)
    thread.start()
