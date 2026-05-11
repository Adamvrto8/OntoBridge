from __future__ import annotations

from fastapi import APIRouter

from ontobridge.api.deps import PublisherDep

router = APIRouter(prefix="/graph", tags=["graph"])


def _last_seg(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]


@router.get("")
def get_graph(publisher: PublisherDep):
    terms = publisher.search_terms("")
    uri_set = {t.term_uri for t in terms}

    nodes = []
    edges = []

    for t in terms:
        et = t.enriched_term
        tp = et.taxonomy_placement
        gov = et.governance_result

        scheme = _last_seg(tp.scheme_uri) if tp and tp.scheme_uri else None

        conflict = False
        severity = "low"
        if gov:
            from ontobridge.agents.governance.models import Severity
            triggered = [f for f in gov.findings if f.triggered]
            if any(f.severity is Severity.BLOCK for f in triggered):
                conflict = True
                severity = "crit"
            elif any(f.severity is Severity.WARN for f in triggered):
                severity = "med"

        nodes.append({
            "id":       t.term_uri,
            "label":    et.preferred_label or _last_seg(t.term_uri) or t.term_uri,
            "status":   t.lifecycle_status.value,
            "scheme":   scheme,
            "severity": severity,
            "conflict": conflict,
        })

        for rel in (et.relations or []):
            if rel.object_uri and rel.object_uri in uri_set:
                edges.append({
                    "source":    t.term_uri,
                    "target":    rel.object_uri,
                    "predicate": getattr(rel, "verb", None) or "—",
                })

    return {"nodes": nodes, "edges": edges}
