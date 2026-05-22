from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from ontobridge.audit.base import AuditLog
from ontobridge.publisher.base import TermPublisher

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(key: str | None = Security(_API_KEY_HEADER)) -> None:
    """Enforce API key auth when ONTOBRIDGE_API_KEY env var is set.

    When the env var is not set the check is skipped entirely — this keeps
    local development and CI working without any configuration.
    """
    required = os.environ.get("ONTOBRIDGE_API_KEY", "")
    if not required:
        return
    if not key or key != required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


AuthDep = Depends(verify_api_key)


def get_publisher(request: Request) -> TermPublisher:
    return request.app.state.publisher


def get_audit_log(request: Request) -> AuditLog:
    return request.app.state.audit_log


def get_ontology(request: Request):
    return request.app.state.ontology


def get_fibo_matcher(request: Request):
    return getattr(request.app.state, "fibo_matcher", None)


PublisherDep = Annotated[TermPublisher, Depends(get_publisher)]
AuditDep = Annotated[AuditLog, Depends(get_audit_log)]
OntologyDep = Annotated[object, Depends(get_ontology)]
FiboMatcherDep = Annotated[object, Depends(get_fibo_matcher)]
