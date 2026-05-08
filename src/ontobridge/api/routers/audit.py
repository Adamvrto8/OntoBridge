from __future__ import annotations

from fastapi import APIRouter

from ontobridge.api.deps import AuditDep
from ontobridge.api.schemas import AuditEntryOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntryOut])
def list_audit(audit: AuditDep, limit: int = 100):
    return [AuditEntryOut.from_entry(e) for e in audit.entries()[:limit]]
