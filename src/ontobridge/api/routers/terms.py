from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import io

from ontobridge.api.deps import AuditDep, PublisherDep
from ontobridge.api.schemas import StatusTransitionRequest, TermDetail, TermSummary
from ontobridge.audit.models import AuditEntry
from ontobridge.export import export_glossary_csv
from ontobridge.models.enums import LifecycleStatus

router = APIRouter(prefix="/terms", tags=["terms"])

_STATUS_MAP = {s.value: s for s in LifecycleStatus}


@router.get("", response_model=list[TermSummary])
def list_terms(
    publisher: PublisherDep,
    search: str = "",
    status: str | None = None,
):
    terms = publisher.search_terms(search)
    if status:
        target = _STATUS_MAP.get(status)
        if target:
            terms = [t for t in terms if t.lifecycle_status is target]
    return [TermSummary.from_published(t) for t in terms]


@router.get("/export/csv")
def export_csv(publisher: PublisherDep, status: str | None = None):
    statuses = [_STATUS_MAP[status]] if status and status in _STATUS_MAP else None
    csv_text = export_glossary_csv(publisher, statuses=statuses)
    return StreamingResponse(
        io.StringIO(csv_text),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=glossary.csv"},
    )


@router.get("/{term_id:path}", response_model=TermDetail)
def get_term(term_id: str, publisher: PublisherDep):
    try:
        term = publisher.get_term(term_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Term not found")
    return TermDetail.from_published(term)


@router.patch("/{term_id:path}/status", response_model=TermSummary)
def transition_status(
    term_id: str,
    body: StatusTransitionRequest,
    publisher: PublisherDep,
    audit: AuditDep,
):
    try:
        term = publisher.get_term(term_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Term not found")

    new_status = _STATUS_MAP.get(body.new_status)
    if not new_status:
        raise HTTPException(status_code=422, detail=f"Unknown status: {body.new_status}")

    previous = term.lifecycle_status
    try:
        updated = publisher.transition_status(term_id, new_status, approved_by=body.actor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    audit.record(AuditEntry(
        term_uri=term_id,
        term_label=term.enriched_term.preferred_label or term_id,
        action=body.new_status,
        actor=body.actor,
        previous_status=previous,
        new_status=new_status,
        comment=body.comment,
    ))

    return TermSummary.from_published(updated)
