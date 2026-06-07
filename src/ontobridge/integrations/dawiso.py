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
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ontobridge.models.enrichment import EnrichedTerm
    from ontobridge.models.published import PublishedTerm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dawiso object / attribute type IDs (Business Glossary, applicationId=4)
# ---------------------------------------------------------------------------
_OT_DOMAIN  = 21   # Business Domain
_OT_TERM    = 22   # Business Term
_OT_SYNONYM = 25   # Synonym

_ATTR_DEF   = 27   # core_business_glossary_definition

# Maps FIBO module abbreviations → OntoBridge ontology scheme names
# so FIBO-placed terms land in meaningful Dawiso domains
_FIBO_MODULE_TO_SCHEME: dict[str, str] = {
    "FBC": "Compliance",
    "FND": "Organisation",
    "LOAN": "Product",
    "SEC": "Product",
    "BE":  "Organisation",
    "IND": "Risk",
    "DER": "Product",
    "BP":  "Process",
    "CAE": "Process",
    "MD":  "Risk",
    "ACTUS": "Product",
}

@dataclass
class DawisoTermInfo:
    object_id: int
    name: str
    alt_labels: list[str]


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
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {jwt}"
        }
        self._space_id = space_id
        self._app_id = application_id
        self._domain_cache: dict[str, int] = {}  # scheme_label → domain objectId
        self._domain_lock = threading.Lock()  # prevents concurrent duplicate domain creation

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_scheme_label(self, term: "PublishedTerm | EnrichedTerm") -> str:
        et = getattr(term, "enriched_term", term)
        tp = et.taxonomy_placement
        scheme_label = "OntoBridge"
        if tp and tp.scheme_uri:
            seg = tp.scheme_uri.rstrip("/").rsplit("/", 1)[-1]
            clean = seg.removesuffix("Scheme").removeprefix("Scheme")
            scheme_label = _FIBO_MODULE_TO_SCHEME.get(clean, clean) or seg or "OntoBridge"
        return scheme_label

    def find_domain(self, scheme_label: str) -> int | None:
        import httpx
        try:
            with httpx.Client(base_url=self._base, headers=self._headers, timeout=30) as client:
                return self._search_domain(client, scheme_label)
        except Exception as exc:
            logger.debug("Dawiso find_domain failed: %s", exc)
            return None

    def find_term(self, domain_id: int, term_name: str) -> DawisoTermInfo | None:
        import httpx
        try:
            with httpx.Client(base_url=self._base, headers=self._headers, timeout=30) as client:
                return self._find_term_with_client(client, domain_id, term_name)
        except Exception as exc:
            logger.debug("Dawiso find_term failed: %s", exc)
        return None

    def _record_name(self, record: dict) -> str:
        return str(record.get("objectName") or record.get("name") or "").strip()

    def _find_term_with_client(self, client, domain_id: int, term_name: str) -> DawisoTermInfo | None:
        r = client.post("/api/mr-object/filter", json={
            "filter": {
                "objectTypeId": _OT_TERM,
                "parentObjectId": domain_id,
                "spaceId": self._space_id,
                "applicationId": self._app_id,
                "objectName": term_name,
            },
            "take": 1,
        })
        if r.is_success:
            data = r.json().get("data", [])
            if data:
                return DawisoTermInfo(
                    object_id=data[0]["objectId"],
                    name=self._record_name(data[0]),
                    alt_labels=[],
                )

        # If no exact business term was found, try matching a synonym object.
        # Synonyms are stored as separate objects under the term, so we need
        # to search _OT_SYNONYM objects by name and resolve the parent term.
        r = client.post("/api/mr-object/filter", json={
            "filter": {
                "objectTypeId": _OT_SYNONYM,
                "spaceId": self._space_id,
                "applicationId": self._app_id,
                "objectName": term_name,
            },
            "take": 1,
        })
        if r.is_success:
            data = r.json().get("data", [])
            if data:
                synonym_record = data[0]
                parent_id = synonym_record.get("parentObjectId")
                if parent_id:
                    return DawisoTermInfo(
                        object_id=parent_id,
                        name=synonym_record.get("objectName", ""),
                        alt_labels=[],
                    )
        return None

    def _find_existing_term_id(self, client, domain_id: int, term: "PublishedTerm") -> int | None:
        et = term.enriched_term
        if not et.candidate_labels:
            return None

        seen: set[str] = set()
        for candidate in [et.preferred_label] + [cl.text for cl in et.candidate_labels]:
            if not candidate:
                continue
            key = candidate.casefold()
            if key in seen:
                continue
            seen.add(key)
            existing = self._find_term_with_client(client, domain_id, candidate)
            if existing:
                return existing.object_id
        return None

    def publish_or_update(self, term: "PublishedTerm") -> str | None:
        return self.publish(term)

    def publish(self, term: "PublishedTerm") -> str | None:
        """Publish a term to Dawiso. Returns the Dawiso object URL or None on failure."""
        import httpx

        et = term.enriched_term
        label = et.preferred_label or ""
        definition = et.definition or ""
        if not label:
            return None

        scheme_label = self.get_scheme_label(term)

        alt_labels = [
            cl.text for cl in et.candidate_labels
            if cl.text != label and cl.text.strip()
        ]

        try:
            with httpx.Client(
                base_url=self._base,
                cookies=self._cookies,
                headers=self._headers,
                timeout=30,
            ) as client:
                domain_id = self._get_or_create_domain(client, scheme_label)
                object_id = getattr(et, "dawiso_object_id", None)
                if object_id is None:
                    object_id = self._find_existing_term_id(client, domain_id, term)

                action = getattr(et, "dawiso_sync_action", "create")
                if action == "update" and object_id is not None:
                    self._update_term(client, object_id, definition, alt_labels)
                    term_id = object_id
                else:
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

    # ------------------------------------------------------------------
    # Domain management
    # ------------------------------------------------------------------

    def _get_or_create_domain(self, client, scheme_label: str) -> int:
        with self._domain_lock:
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
                    if self._record_name(item).lower() == name.lower():
                        return item["objectId"]
        except Exception as exc:
            logger.debug("Dawiso domain search failed: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Object creation
    # ------------------------------------------------------------------

    def _update_attribute(self, client, object_id: int, attr_type_id: int, text_value: str) -> None:
        payload = {"textValue": text_value, "value": text_value}
        r = client.put(f"/api/mr-object/{object_id}/attribute/{attr_type_id}", json=payload)
        if not r.is_success:
            print(f"\n[DAWISO UPDATE ERROR] {r.status_code}: {r.text}\n")
        r.raise_for_status()

    def _find_synonym_with_client(self, client, term_id: int, name: str) -> int | None:
        try:
            r = client.post("/api/mr-object/filter", json={
                "filter": {
                    "objectTypeId": _OT_SYNONYM,
                    "parentObjectId": term_id,
                    "spaceId": self._space_id,
                    "applicationId": self._app_id,
                    "objectName": name,
                },
                "take": 1,
            })
            if r.is_success:
                data = r.json().get("data", [])
                if data:
                    return data[0].get("objectId")
        except Exception as exc:
            logger.debug("Dawiso synonym lookup failed for '%s' (term=%d): %s", name, term_id, exc)
        return None

    def _update_term(self, client, term_id: int, definition: str | None, alt_labels: list[str] | None) -> None:
        if definition:
            try:
                self._update_attribute(client, term_id, _ATTR_DEF, definition)
            except Exception as exc:
                print(f"\n[DAWISO UPDATE FAILED] Zlyhala aktualizacia definicie (objectId={term_id}): {exc}\n")
                logger.warning("Dawiso definition update skipped for objectId=%d: %s", term_id, exc)

        if alt_labels:
            seen: set[str] = set()
            for alt in alt_labels:
                label = alt.strip()
                if not label:
                    continue
                key = label.casefold()
                if key in seen:
                    continue
                seen.add(key)
                if self._find_synonym_with_client(client, term_id, label) is None:
                    self._create_synonym(client, label, term_id)

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
            "objectName": name,
            "spaceId": self._space_id,
            "applicationId": self._app_id,
            "attributes": attributes or [],
        }
        if parent_object_id is not None:
            payload["parentObjectId"] = parent_object_id
            
        r = client.post("/api/mr-object", json=payload)
        if not r.is_success:
            print(f"\n[DAWISO API ERROR] Zlyhalo vytvorenie objektu '{name}'.\nHTTP {r.status_code}: {r.text}\n")
        r.raise_for_status()
        return r.json()["objectId"]


# ---------------------------------------------------------------------------
# Dawiso Sync Agent for Pipeline
# ---------------------------------------------------------------------------

class DawisoSyncAgent:
    """Agent for checking the catalog state before publishing.

    Maintains a single persistent httpx.Client and a domain-ID cache for the
    lifetime of the pipeline run so that N terms in the same scheme produce only
    1 domain lookup and all term-existence checks reuse the same TCP connection.
    """

    def __init__(self, publisher: DawisoPublisher | None = None):
        self.publisher = publisher
        self._domain_cache: dict[str, int | None] = {}
        self._client = None

    def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.Client(
                base_url=self.publisher._base,
                headers=self.publisher._headers,
                cookies=self.publisher._cookies,
                timeout=30,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def apply(self, term: "EnrichedTerm") -> "EnrichedTerm":
        if not self.publisher:
            return term
        try:
            client = self._get_client()
        except Exception:
            return term

        scheme_label = self.publisher.get_scheme_label(term)

        if scheme_label not in self._domain_cache:
            try:
                self._domain_cache[scheme_label] = self.publisher._search_domain(client, scheme_label)
            except Exception:
                self._domain_cache[scheme_label] = None

        domain_id = self._domain_cache[scheme_label]
        term.dawiso_domain_id = domain_id
        term.dawiso_object_id = None
        term.dawiso_sync_action = "create"
        term.dawiso_existing_labels = []

        if domain_id and term.candidate_labels:
            existing = None
            for candidate in [term.preferred_label] + [cl.text for cl in term.candidate_labels]:
                if not candidate:
                    continue
                try:
                    existing = self.publisher._find_term_with_client(client, domain_id, candidate)
                except Exception:
                    pass
                if existing:
                    break
            if existing:
                term.dawiso_object_id = existing.object_id
                term.dawiso_sync_action = "update"
                term.dawiso_existing_labels = [existing.name] + existing.alt_labels
        return term


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
