"""Dawiso integration test — runs against the real API.

Usage:
    python tests/integration_dawiso.py

Requires env vars from .env:
    DAWISO_URL, DAWISO_JWT, DAWISO_SESSION_ID, DAWISO_SPACE_ID
"""
from __future__ import annotations

import os
import sys
import traceback

from dotenv import load_dotenv

load_dotenv()

import httpx

URL        = os.environ["DAWISO_URL"].rstrip("/")
JWT        = os.environ["DAWISO_JWT"]
SESSION_ID = os.environ.get("DAWISO_SESSION_ID", "")
SPACE_ID   = int(os.environ.get("DAWISO_SPACE_ID", "166"))
APP_ID     = int(os.environ.get("DAWISO_APP_ID", "4"))

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {JWT}",
}
COOKIES = {"jwt": JWT, "session_id": SESSION_ID}

TEST_DOMAIN = "OntoBridge-Test"
TEST_TERM   = "OntoBridge IntegrationTest Term"
TEST_DEF    = "Temporary term created by OntoBridge integration test. Safe to delete."
TEST_ALT    = "OB-Test-Alias"

_PASS = "  [PASS]"
_FAIL = "  [FAIL]"
_INFO = "  [INFO]"

errors: list[str] = []


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def ok(msg: str) -> None:
    print(f"{_PASS} {msg}")


def fail(msg: str) -> None:
    print(f"{_FAIL} {msg}")
    errors.append(msg)


def info(msg: str) -> None:
    print(f"{_INFO} {msg}")


# ---------------------------------------------------------------------------
# 1. CONNECTIVITY
# ---------------------------------------------------------------------------

section("1. Connectivity")

try:
    with httpx.Client(base_url=URL, headers=HEADERS, cookies=COOKIES, timeout=15) as c:
        r = c.post("/api/mr-object/filter", json={
            "filter": {"objectTypeId": 21, "applicationId": APP_ID, "spaceId": SPACE_ID},
            "take": 1,
        })
    if r.is_success:
        ok(f"Connected to {URL} — HTTP {r.status_code}")
    else:
        fail(f"HTTP {r.status_code}: {r.text[:200]}")
except Exception as e:
    fail(f"Connection error: {e}")
    traceback.print_exc()
    sys.exit(1)


# ---------------------------------------------------------------------------
# 2. READ — list existing Business Domains
# ---------------------------------------------------------------------------

section("2. Read — existing Business Domains")

existing_domains: list[dict] = []
try:
    with httpx.Client(base_url=URL, headers=HEADERS, cookies=COOKIES, timeout=15) as c:
        r = c.post("/api/mr-object/filter", json={
            "filter": {"objectTypeId": 21, "applicationId": APP_ID, "spaceId": SPACE_ID},
            "take": 50,
        })
    r.raise_for_status()
    existing_domains = r.json().get("data", [])
    if existing_domains:
        ok(f"Found {len(existing_domains)} domain(s):")
        for d in existing_domains[:10]:
            name = d.get("objectName") or d.get("name") or "(no name)"
            info(f"  domain objectId={d['objectId']}  name={name!r}")
        if len(existing_domains) > 10:
            info(f"  ... and {len(existing_domains)-10} more")
    else:
        info("No existing domains found (space may be empty)")
except Exception as e:
    fail(f"Domain listing failed: {e}")


# ---------------------------------------------------------------------------
# 3. READ — find a term in an existing domain (first domain, first term)
# ---------------------------------------------------------------------------

section("3. Read — find Business Terms in first domain")

if existing_domains:
    first_domain = existing_domains[0]
    first_domain_id = first_domain["objectId"]
    first_domain_name = first_domain.get("objectName") or first_domain.get("name") or "?"
    try:
        with httpx.Client(base_url=URL, headers=HEADERS, cookies=COOKIES, timeout=15) as c:
            r = c.post("/api/mr-object/filter", json={
                "filter": {
                    "objectTypeId": 22,
                    "parentObjectId": first_domain_id,
                    "applicationId": APP_ID,
                    "spaceId": SPACE_ID,
                },
                "take": 5,
            })
        r.raise_for_status()
        terms = r.json().get("data", [])
        if terms:
            ok(f"Domain {first_domain_name!r} (id={first_domain_id}) has {len(terms)} term(s) (showing up to 5):")
            for t in terms:
                info(f"  term objectId={t['objectId']}  name={t.get('objectName') or t.get('name')!r}")
        else:
            info(f"Domain {first_domain_name!r} has no terms yet")
    except Exception as e:
        fail(f"Term listing failed: {e}")
else:
    info("Skipped — no domains to inspect")


# ---------------------------------------------------------------------------
# 4. WRITE — create test domain (or reuse existing)
# ---------------------------------------------------------------------------

section("4. Write — create/find test domain")

test_domain_id: int | None = None

def _find_domain(name: str) -> int | None:
    with httpx.Client(base_url=URL, headers=HEADERS, cookies=COOKIES, timeout=15) as c:
        r = c.post("/api/mr-object/filter", json={
            "filter": {"objectTypeId": 21, "applicationId": APP_ID, "spaceId": SPACE_ID, "objectName": name},
            "take": 10,
        })
    if r.is_success:
        for item in r.json().get("data", []):
            n = (item.get("objectName") or item.get("name") or "").strip()
            if n.lower() == name.lower():
                return item["objectId"]
    return None

try:
    existing_id = _find_domain(TEST_DOMAIN)
    if existing_id:
        test_domain_id = existing_id
        ok(f"Reusing existing test domain {TEST_DOMAIN!r} (id={test_domain_id})")
    else:
        with httpx.Client(base_url=URL, headers=HEADERS, cookies=COOKIES, timeout=15) as c:
            r = c.post("/api/mr-object", json={
                "objectTypeId": 21,
                "name": TEST_DOMAIN,
                "objectName": TEST_DOMAIN,
                "spaceId": SPACE_ID,
                "applicationId": APP_ID,
                "attributes": [],
            })
        if not r.is_success:
            fail(f"Domain create HTTP {r.status_code}: {r.text[:300]}")
        else:
            test_domain_id = r.json()["objectId"]
            ok(f"Created test domain {TEST_DOMAIN!r} (id={test_domain_id})")
except Exception as e:
    fail(f"Domain create/find failed: {e}")
    traceback.print_exc()


# ---------------------------------------------------------------------------
# 5. WRITE — create test term with definition + synonym
# ---------------------------------------------------------------------------

section("5. Write — create Business Term")

test_term_id: int | None = None

if test_domain_id is not None:
    # Check if test term already exists (idempotent)
    def _find_term(domain_id: int, name: str) -> int | None:
        with httpx.Client(base_url=URL, headers=HEADERS, cookies=COOKIES, timeout=15) as c:
            r = c.post("/api/mr-object/filter", json={
                "filter": {
                    "objectTypeId": 22,
                    "parentObjectId": domain_id,
                    "applicationId": APP_ID,
                    "spaceId": SPACE_ID,
                    "objectName": name,
                },
                "take": 1,
            })
        if r.is_success:
            data = r.json().get("data", [])
            if data:
                return data[0]["objectId"]
        return None

    try:
        existing_term_id = _find_term(test_domain_id, TEST_TERM)
        if existing_term_id:
            test_term_id = existing_term_id
            ok(f"Test term already exists (id={test_term_id}), reusing")
        else:
            with httpx.Client(base_url=URL, headers=HEADERS, cookies=COOKIES, timeout=15) as c:
                r = c.post("/api/mr-object", json={
                    "objectTypeId": 22,
                    "name": TEST_TERM,
                    "objectName": TEST_TERM,
                    "parentObjectId": test_domain_id,
                    "spaceId": SPACE_ID,
                    "applicationId": APP_ID,
                    "attributes": [{"attributeTypeId": 27, "textValue": TEST_DEF}],
                })
            if not r.is_success:
                fail(f"Term create HTTP {r.status_code}: {r.text[:300]}")
            else:
                test_term_id = r.json()["objectId"]
                ok(f"Created test term {TEST_TERM!r} (id={test_term_id})")
    except Exception as e:
        fail(f"Term create failed: {e}")
        traceback.print_exc()
else:
    info("Skipped — no test domain")


# ---------------------------------------------------------------------------
# 6. WRITE — create synonym under the test term
# ---------------------------------------------------------------------------

section("6. Write — create Synonym")

if test_term_id is not None:
    try:
        with httpx.Client(base_url=URL, headers=HEADERS, cookies=COOKIES, timeout=15) as c:
            r = c.post("/api/mr-object/filter", json={
                "filter": {
                    "objectTypeId": 25,
                    "parentObjectId": test_term_id,
                    "applicationId": APP_ID,
                    "spaceId": SPACE_ID,
                    "objectName": TEST_ALT,
                },
                "take": 1,
            })
        existing_syn = r.json().get("data", []) if r.is_success else []

        if existing_syn:
            ok(f"Synonym {TEST_ALT!r} already exists (id={existing_syn[0]['objectId']})")
        else:
            with httpx.Client(base_url=URL, headers=HEADERS, cookies=COOKIES, timeout=15) as c:
                r = c.post("/api/mr-object", json={
                    "objectTypeId": 25,
                    "name": TEST_ALT,
                    "objectName": TEST_ALT,
                    "parentObjectId": test_term_id,
                    "spaceId": SPACE_ID,
                    "applicationId": APP_ID,
                    "attributes": [],
                })
            if not r.is_success:
                fail(f"Synonym create HTTP {r.status_code}: {r.text[:300]}")
            else:
                syn_id = r.json()["objectId"]
                ok(f"Created synonym {TEST_ALT!r} (id={syn_id})")
    except Exception as e:
        fail(f"Synonym create failed: {e}")
else:
    info("Skipped — no test term")


# ---------------------------------------------------------------------------
# 7. WRITE — update definition
# ---------------------------------------------------------------------------

section("7. Write — update definition (PUT attribute)")

if test_term_id is not None:
    updated_def = TEST_DEF + " [UPDATED]"
    try:
        with httpx.Client(base_url=URL, headers=HEADERS, cookies=COOKIES, timeout=15) as c:
            r = c.put(f"/api/mr-object/{test_term_id}/attribute/27", json={
                "textValue": updated_def,
                "value": updated_def,
            })
        if r.is_success:
            ok(f"Definition updated on objectId={test_term_id}")
        else:
            fail(f"Update HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        fail(f"Update failed: {e}")
else:
    info("Skipped — no test term")


# ---------------------------------------------------------------------------
# 8. VERIFY — read back the term to confirm it exists
# ---------------------------------------------------------------------------

section("8. Verify — read back test term")

if test_term_id is not None and test_domain_id is not None:
    try:
        found_id = _find_term(test_domain_id, TEST_TERM)
        if found_id == test_term_id:
            ok(f"Term {TEST_TERM!r} confirmed in Dawiso (id={found_id})")
        elif found_id:
            fail(f"Term found but wrong id: expected {test_term_id}, got {found_id}")
        else:
            fail(f"Term {TEST_TERM!r} not found after creation!")
    except Exception as e:
        fail(f"Verify failed: {e}")
else:
    info("Skipped")


# ---------------------------------------------------------------------------
# 9. END-TO-END — DawisoPublisher.publish()
# ---------------------------------------------------------------------------

section("9. End-to-end — DawisoPublisher.publish() via pipeline integration")

from ontobridge.integrations.dawiso import DawisoPublisher
from ontobridge.models import CandidateLabel, EnrichedTerm, HarvestRecord, SourceRef, SourceType, Tier
from ontobridge.models.published import PublishedTerm

publisher = DawisoPublisher(URL, JWT, SESSION_ID, SPACE_ID, APP_ID)

hr = HarvestRecord(
    text="test",
    source_type=SourceType.USER_INPUT,
    source_ref=SourceRef(source_system="integration-test"),
    tier=Tier.UNSTRUCTURED,
)
et = EnrichedTerm.from_harvest(hr)
et.candidate_labels = [
    CandidateLabel(text="OntoBridge E2E Test Term", confidence=0.9),
    CandidateLabel(text="OB-E2E-Alias", confidence=0.7),
]
et.definition = "E2E test term created by DawisoPublisher.publish(). Safe to delete."
et.dawiso_sync_action = "create"

from dataclasses import replace
from ontobridge.models.enums import LifecycleStatus

pt = PublishedTerm(
    term_uri="http://ontobridge.dev/ontology/bank/OntoBridgeE2ETestTerm",
    enriched_term=et,
    lifecycle_status=LifecycleStatus.REVIEW,
)

try:
    url = publisher.publish(pt)
    if url:
        ok(f"DawisoPublisher.publish() returned URL:\n  {_INFO} {url}")
    else:
        fail("DawisoPublisher.publish() returned None — check logs above for details")
except Exception as e:
    fail(f"DawisoPublisher.publish() raised: {e}")
    traceback.print_exc()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

section("SUMMARY")

if errors:
    print(f"\n  {len(errors)} test(s) FAILED:")
    for e in errors:
        print(f"  - {e}")
    print()
    sys.exit(1)
else:
    print("\n  Vsetky testy PASSED.")
    print(f"\n  Poznamka: testovaci domain '{TEST_DOMAIN}' a termy zostali v Dawiso.")
    print("  Mozete ich rucne zmazat cez Dawiso UI ak chcete.")
    print()
    sys.exit(0)
