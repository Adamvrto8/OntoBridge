"""Dawiso Business Glossary publisher.

Publishes approved OntoBridge terms to Dawiso's Business Glossary
as Business Terms, using Dawiso's REST API.

Configuration (env vars):
    DAWISO_URL          Base URL of the Dawiso instance
                        e.g. https://vse-demo.dawiso.cloud
    DAWISO_TOKEN        Bearer JWT token for authentication
    DAWISO_SPACE_ID     Numeric ID of the target Dawiso space (default: 166)
    DAWISO_APP_ID       Business Glossary application ID (default: 4)

Mapping:
    OntoBridge scheme_label  →  Dawiso Business Domain (objectTypeId 21)
    OntoBridge preferred_label + definition  →  Dawiso Business Term (objectTypeId 22)
    OntoBridge alt_labels   →  Dawiso Synonyms (objectTypeId 25)

Delivery is fire-and-forget (background thread). Failures are logged
but never raise — the term approval flow is never blocked.

Enable it:
    $env:DAWISO_URL   = "https://vse-demo.dawiso.cloud"
    $env:DAWISO_TOKEN = "your-jwt-token"
    $env:DAWISO_SPACE_ID = "166"
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
# Dawiso object type IDs (Business Glossary application)
# ---------------------------------------------------------------------------
_OT_DOMAIN = 21   # Business Domain — top-level category (maps to scheme)
_OT_TERM   = 22   # Business Term   — the actual term
_OT_SYNONYM = 25  # Synonym         — alt labels

# Attribute type IDs
_ATTR_DEFINITION = 27   # core_business_glossary_definition


class DawisoPublisher:
    """Publishes OntoBridge terms to Dawiso Business Glossary via REST API.

    Domains (scheme → Business Domain) are cached in memory for the lifetime
    of the publisher instance so each scheme only results in one search call.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        space_id: int,
        application_id: int = 4,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._space_id = space_id
        self._app_id = application_id
        self._domain_cache: dict[str, int] = {}  # scheme_label → domain objectId

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish(self, term: "PublishedTerm") -> str | None:
        """Publish a term to Dawiso. Returns the Dawiso object URL or None on failure.

        Runs synchronously — call via fire() for background delivery.
        """
        import httpx

        et = term.enriched_term
        label = et.preferred_label or ""
        definition = et.definition or ""
        if not label:
            return None

        # Derive scheme label for the Business Domain
        tp = et.taxonomy_placement
        scheme_label = "OntoBridge"
        if tp and tp.scheme_uri:
            seg = tp.scheme_uri.rstrip("/").rsplit("/", 1)[-1]
            scheme_label = seg.removeprefix("Scheme") or seg or "OntoBridge"

        alt_labels = [
            cl.text for cl in et.candidate_labels
            if cl.text != label and cl.text.strip()
        ]

        try:
            with httpx.Client(
                base_url=self._base,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=30,
            ) as client:
                domain_id = self._get_or_create_domain(client, scheme_label)
                term_id = self._create_term(client, label, domain_id)
                self._set_definition(client, term_id, definition)
                for alt in alt_labels[:10]:  # cap at 10 synonyms
                    self._create_synonym(client, alt, term_id)

            url = (
                f"{self._base}/data-governance/space/{self._space_id}/-"
                f"/app/{self._app_id}/-/object/{term_id}/-"
            )
            logger.info("Dawiso: published '%s' → %s", label, url)
            return url

        except Exception as exc:
            logger.warning("Dawiso publish failed for '%s': %s", label, exc)
            return None

    def fire(self, term: "PublishedTerm") -> None:
        """Publish in a background thread — never blocks the caller."""
        thread = threading.Thread(target=self.publish, args=(term,), daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # REST helpers
    # ------------------------------------------------------------------

    def _get_or_create_domain(self, client, scheme_label: str) -> int:
        if scheme_label in self._domain_cache:
            return self._domain_cache[scheme_label]

        # Search for existing Business Domain with this name
        domain_id = self._search_domain(client, scheme_label)
        if domain_id is None:
            domain_id = self._create_object(
                client,
                object_type_id=_OT_DOMAIN,
                name=scheme_label,
                parent_object_id=0,  # root level
            )

        self._domain_cache[scheme_label] = domain_id
        return domain_id

    def _search_domain(self, client, name: str) -> int | None:
        """Find an existing Business Domain by name. Returns objectId or None."""
        try:
            r = client.post(
                "/api/public/v1/objects/filter",
                json={
                    "objectTypeIds": [_OT_DOMAIN],
                    "applicationId": self._app_id,
                    "spaceIds": [self._space_id],
                    "objectName": name,
                    "take": 1,
                },
            )
            r.raise_for_status()
            data = r.json()
            items = data.get("data") or data.get("items") or data.get("result", {}).get("data", [])
            for item in items:
                if item.get("objectName", "").lower() == name.lower():
                    return item["objectId"]
        except Exception as exc:
            logger.debug("Dawiso domain search failed: %s", exc)
        return None

    def _create_term(self, client, name: str, domain_id: int) -> int:
        return self._create_object(
            client,
            object_type_id=_OT_TERM,
            name=name,
            parent_object_id=domain_id,
        )

    def _create_synonym(self, client, name: str, term_id: int) -> None:
        try:
            self._create_object(
                client,
                object_type_id=_OT_SYNONYM,
                name=name,
                parent_object_id=term_id,
            )
        except Exception as exc:
            logger.debug("Dawiso synonym '%s' failed: %s", name, exc)

    def _create_object(
        self,
        client,
        object_type_id: int,
        name: str,
        parent_object_id: int,
    ) -> int:
        payload = {
            "objectTypeId": object_type_id,
            "name": name,
            "parentObjectId": parent_object_id,
            "spaceId": self._space_id,
            "applicationId": self._app_id,
        }
        r = client.post("/api/public/v1/objects", json=payload)
        if not r.is_success:
            # Try alternate endpoint pattern
            r = client.post("/api/object", json=payload)
        r.raise_for_status()
        data = r.json()
        result = data.get("result", data)
        return result["objectId"]

    def _set_definition(self, client, object_id: int, definition: str) -> None:
        if not definition:
            return
        payload = {"objectId": object_id, "attributeTypeId": _ATTR_DEFINITION, "textValue": definition}
        # Try multiple endpoint patterns — Dawiso API path varies by version
        for path in (
            f"/api/public/v1/objects/{object_id}/attributes/{_ATTR_DEFINITION}",
            "/api/public/v1/attribute-values",
            f"/api/attribute-value/{object_id}/{_ATTR_DEFINITION}",
        ):
            try:
                r = client.put(path, json=payload) if "attributes" in path else client.post(path, json=payload)
                if r.is_success:
                    return
            except Exception:
                continue
        logger.debug("Dawiso: could not set definition on object %d", object_id)


# ---------------------------------------------------------------------------
# Module-level singleton — built from env vars, None when unconfigured
# ---------------------------------------------------------------------------

_publisher: DawisoPublisher | None = None
_publisher_built = False


def get_publisher() -> DawisoPublisher | None:
    """Return the configured DawisoPublisher, or None if env vars are not set."""
    global _publisher, _publisher_built
    if _publisher_built:
        return _publisher
    _publisher_built = True

    url = os.environ.get("DAWISO_URL", "").strip()
    token = os.environ.get("DAWISO_TOKEN", "").strip()
    if not url or not token:
        return None

    space_id = int(os.environ.get("DAWISO_SPACE_ID", "166"))
    app_id = int(os.environ.get("DAWISO_APP_ID", "4"))
    _publisher = DawisoPublisher(url, token, space_id, app_id)
    logger.info("Dawiso publisher enabled → %s (space=%d)", url, space_id)
    return _publisher
