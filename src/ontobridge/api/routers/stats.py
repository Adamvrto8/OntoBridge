from __future__ import annotations

from fastapi import APIRouter

from ontobridge.api.deps import AuditDep, OntologyDep, PublisherDep
from ontobridge.api.schemas import OntologyConceptOut, StatsOut, _resolve_scheme_label
from ontobridge.models.enums import LifecycleStatus

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/concepts", response_model=list[OntologyConceptOut])
def list_concepts(ontology: OntologyDep):
    return [
        OntologyConceptOut(
            uri=c.uri,
            pref_label=c.pref_label,
            scheme_uri=c.scheme,
            scheme_label=c.scheme_label,
        )
        for c in sorted(ontology.concepts, key=lambda c: (c.scheme_label or "", c.pref_label))
    ]


@router.get("/verbs", response_model=list[str])
def list_verbs(ontology: OntologyDep):
    pairs = ontology.object_property_pairs()
    verbs: set[str] = set()
    for p in pairs:
        verbs.add(p.forward_label)
        verbs.add(p.inverse_label)
    return sorted(verbs)


@router.get("", response_model=StatsOut)
def get_stats(publisher: PublisherDep, audit: AuditDep, ontology: OntologyDep):
    terms = publisher.search_terms("")

    by_status: dict[str, int] = {s.value: 0 for s in LifecycleStatus}
    by_scheme: dict[str, int] = {}  # term count per scheme (human label)
    with_definition = 0

    for t in terms:
        by_status[t.lifecycle_status.value] = by_status.get(t.lifecycle_status.value, 0) + 1
        tp = t.enriched_term.taxonomy_placement
        label = (_resolve_scheme_label(tp.scheme_uri, ontology) if tp and tp.scheme_uri else None) or "Uncategorised"
        by_scheme[label] = by_scheme.get(label, 0) + 1
        if t.enriched_term.definition:
            with_definition += 1

    return StatsOut(
        total=len(terms),
        by_status={k: v for k, v in by_status.items() if v > 0},
        by_scheme=by_scheme,
        recent_activity=audit.count(),
        with_definition=with_definition,
    )
