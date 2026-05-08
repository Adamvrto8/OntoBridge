from __future__ import annotations

from fastapi import APIRouter

from ontobridge.api.deps import AuditDep, PublisherDep
from ontobridge.api.schemas import StatsOut
from ontobridge.models.enums import LifecycleStatus

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
def get_stats(publisher: PublisherDep, audit: AuditDep):
    terms = publisher.search_terms("")

    by_status: dict[str, int] = {s.value: 0 for s in LifecycleStatus}
    scheme_total: dict[str, int] = {}
    scheme_with_def: dict[str, int] = {}

    for t in terms:
        by_status[t.lifecycle_status.value] = by_status.get(t.lifecycle_status.value, 0) + 1
        tp = t.enriched_term.taxonomy_placement
        label = "Uncategorised"
        if tp and tp.scheme_uri:
            label = tp.scheme_uri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        scheme_total[label] = scheme_total.get(label, 0) + 1
        if t.enriched_term.definition:
            scheme_with_def[label] = scheme_with_def.get(label, 0) + 1

    by_scheme = {
        label: round(scheme_with_def.get(label, 0) / total * 100)
        for label, total in scheme_total.items()
    }

    return StatsOut(
        total=len(terms),
        by_status={k: v for k, v in by_status.items() if v > 0},
        by_scheme=by_scheme,
        recent_activity=audit.count(),
    )
