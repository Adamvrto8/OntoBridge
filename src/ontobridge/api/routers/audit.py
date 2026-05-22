from __future__ import annotations

from fastapi import APIRouter

from ontobridge.api.deps import AuditDep
from ontobridge.api.schemas import AuditEntryOut, PagedResponse

router = APIRouter(prefix="/audit", tags=["audit"])

_MAX_LIMIT = 500


@router.get("", response_model=PagedResponse[AuditEntryOut])
def list_audit(audit: AuditDep, limit: int = 100, offset: int = 0):
    limit = max(1, min(limit, _MAX_LIMIT))
    offset = max(0, offset)
    all_entries = audit.entries()
    total = len(all_entries)
    page = all_entries[offset: offset + limit]
    return PagedResponse(
        items=[AuditEntryOut.from_entry(e) for e in page],
        total=total,
        limit=limit,
        offset=offset,
    )
