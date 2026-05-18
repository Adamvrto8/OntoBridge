from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from ontobridge.audit.base import AuditLog
from ontobridge.publisher.base import TermPublisher


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
