"""Dawiso Business Glossary publisher.

Publishes approved OntoBridge terms to Dawiso's Business Glossary
as Business Terms, using Dawiso's REST API.

Authentication:
    Dawiso's REST API uses cookie-based auth (not Bearer token).
    You need two cookies from your Dawiso browser session:
      - jwt        — the JWT token (value of the `jwt` cookie)
      - session_id — the session identifier (value of `session_id` cookie)

    How to get them: open Dawiso in your browser, open DevTools → Network,
    click any request, copy the Cookie header values for `jwt` and `session_id`.

Configuration (env vars):
    DAWISO_URL          Base URL, e.g. https://vse-demo.dawiso.cloud
    DAWISO_JWT          Value of the jwt cookie
    DAWISO_SESSION_ID   Value of the session_id cookie
    DAWISO_SPACE_ID     Numeric space ID (default: 166  = Team - ICM Gen AI)
    DAWISO_APP_ID       Business Glossary application ID (default: 4)

Object type IDs (Business Glossary application, confirmed on vse-demo.dawiso.cloud):
    21 = Business Domain   → maps to OntoBridge scheme_label
    22 = Business Term     → maps to OntoBridge preferred_label + definition
    25 = Synonym           → maps to OntoBridge alt_labels

Attribute type IDs:
    27 = core_business_glossary_definition

REST endpoints discovered from Swagger:
    POST /api/mr-object                 create object
    POST /api/mr-object/filter          search objects
    POST /api/mr-object/{id}/attribute/{attrTypeId}   update single attribute

Delivery is fire-and-forget (background thread). Failures are logged
but never raised — the term approval flow is never blocked.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ontobridge.models.published import PublishedTerm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dawiso object / attribute type IDs (Business Glossary, applicationId=4)
# ---------------------------------------------------------------------------
_OT_DOMAIN  = 21   # Business Domain
_OT_TERM    = 22   # Business Term
_OT_SYNONYM = 25   # Synonym

_ATTR_DEF   = 27   # core_business_glossary_definition


class DawisoPublisher:
    """Publishes OntoBridge approved terms to Dawiso Business Glossary.

    Domains (scheme → Business Domain) are cached for the publisher lifetime
    so each scheme produces only one search+create cycle.
    """

    def __init__(
        self,
        base_url: str,
        jwt: str,
        session_id: str,
        space_id: int,
        application_id: int = 4,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._cookies = {"jwt": jwt, "session_id": session_id}
        self._space_id = space_id
        self._app_id = application_id
        self._domain_cache: dict[str, int] = {}  # scheme_label → domain objectId

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish(self, term: "PublishedTerm") -> str | None:
        """Publish a term to Dawiso. Returns the Dawiso object URL or None on failure."""
        import httpx

        et = term.enriched_term
        label = et.preferred_label or ""
        definition = et.definition or ""
        if not label:
            return None

        # Derive scheme label → Business Domain name
        # e.g. "http://.../bank/RiskScheme" → "Risk"
        #      "http://.../bank/Risk"        → "Risk"
        tp = et.taxonomy_placement
        scheme_label = "OntoBridge"
        if tp and tp.scheme_uri:
            seg = tp.scheme_uri.rstrip("/").rsplit("/", 1)[-1]
            clean = seg.removesuffix("Scheme").removeprefix("Scheme")
            scheme_label = clean or seg or "OntoBridge"

        alt_labels = [
            cl.text for cl in et.candidate_labels
            if cl.text != label and cl.text.strip()
        ]

        try:
            with httpx.Client(
                base_url=self._base,
                cookies=self._cookies,
                headers={"Content-Type": "application/json"},
                timeout=30,
            ) as client:
                domain_id = self._get_or_create_domain(client, scheme_label)
                term_id = self._create_term(client, label, definition, domain_id)
                for alt in alt_labels[:10]:
                    self._create_synonym(client, alt, term_id)

            url = (
                f"{self._base}/data-governance/space/{self._space_id}/-"
                f"/app/{self._app_id}/-/object/{term_id}/-"
            )
            logger.info("Dawiso: published '%s' (objectId=%d) → %s", label, term_id, url)
            return url

        except Exception as exc:
            logger.warning("Dawiso publish failed for '%s': %s", label, exc)
            return None

    def fire(self, term: "PublishedTerm") -> None:
        """Publish in a background thread — never blocks the caller."""
        thread = threading.Thread(target=self.publish, args=(term,), daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Domain management
    # ------------------------------------------------------------------

    def _get_or_create_domain(self, client, scheme_label: str) -> int:
        if scheme_label in self._domain_cache:
            return self._domain_cache[scheme_label]

        domain_id = self._search_domain(client, scheme_label)
        if domain_id is None:
            # Root-level domains require parentObjectId=None (not 0 — 0 causes 404)
            domain_id = self._create_object(client, _OT_DOMAIN, scheme_label, parent_object_id=None)

        self._domain_cache[scheme_label] = domain_id
        return domain_id

    def _search_domain(self, client, name: str) -> int | None:
        # Filter fields are nested inside "filter" key, and are singular (not arrays)
        try:
            r = client.post("/api/mr-object/filter", json={
                "filter": {
                    "objectTypeId": _OT_DOMAIN,
                    "applicationId": self._app_id,
                    "spaceId": self._space_id,
                    "objectName": name,
                },
                "take": 10,
            })
            if r.is_success:
                for item in r.json().get("data", []):
                    if item.get("objectName", "").strip().lower() == name.lower():
                        return item["objectId"]
        except Exception as exc:
            logger.debug("Dawiso domain search failed: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Object creation
    # ------------------------------------------------------------------

    def _create_term(self, client, name: str, definition: str, domain_id: int) -> int:
        attrs = []
        if definition:
            attrs.append({"attributeTypeId": _ATTR_DEF, "textValue": definition})
        return self._create_object(client, _OT_TERM, name, parent_object_id=domain_id, attributes=attrs)

    def _create_synonym(self, client, name: str, term_id: int) -> None:
        try:
            self._create_object(client, _OT_SYNONYM, name, parent_object_id=term_id)
        except Exception as exc:
            logger.debug("Dawiso synonym '%s' skipped: %s", name, exc)

    def _create_object(
        self,
        client,
        object_type_id: int,
        name: str,
        parent_object_id: int | None,
        attributes: list | None = None,
    ) -> int:
        payload: dict = {
            "objectTypeId": object_type_id,
            "name": name,
            "parentObjectId": parent_object_id,  # None = root level (not 0 — 0 causes 404)
            "spaceId": self._space_id,
            "applicationId": self._app_id,
            "attributes": attributes or [],
        }
        r = client.post("/api/mr-object", json=payload)
        r.raise_for_status()
        return r.json()["objectId"]


# ---------------------------------------------------------------------------
# Module-level singleton built from env vars
# ---------------------------------------------------------------------------

_publisher: DawisoPublisher | None = None
_built = False


def get_publisher() -> DawisoPublisher | None:
    """Return the configured DawisoPublisher, or None when env vars are not set."""
    global _publisher, _built
    if _built:
        return _publisher
    _built = True

    url = os.environ.get("DAWISO_URL", "").strip()
    jwt = os.environ.get("DAWISO_JWT", "").strip()
    session_id = os.environ.get("DAWISO_SESSION_ID", "").strip()

    if not url or not jwt:
        return None

    space_id = int(os.environ.get("DAWISO_SPACE_ID", "166"))
    app_id = int(os.environ.get("DAWISO_APP_ID", "4"))
    _publisher = DawisoPublisher(url, jwt, session_id, space_id, app_id)
    logger.info("Dawiso publisher enabled → %s (space=%d)", url, space_id)
    return _publisher
