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
    by_scheme: dict[str, int] = {}

    for t in terms:
        by_status[t.lifecycle_status.value] = by_status.get(t.lifecycle_status.value, 0) + 1
        tp = t.enriched_term.taxonomy_placement
        scheme = None
        if tp:
            uri = getattr(tp, "broader_uri", None)
            if uri:
                scheme = uri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        label = scheme or "Uncategorised"
        by_scheme[label] = by_scheme.get(label, 0) + 1

    return StatsOut(
        total=len(terms),
        by_status={k: v for k, v in by_status.items() if v > 0},
        by_scheme=by_scheme,
        recent_activity=audit.count(),
    )
