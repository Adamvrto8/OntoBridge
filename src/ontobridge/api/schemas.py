from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TermSummary(BaseModel):
    term_uri: str
    preferred_label: str
    definition: str
    lifecycle_status: str
    scheme: str | None
    scheme_label: str | None
    approved_by: str | None
    version: int
    source_system: str | None

    @classmethod
    def from_published(cls, t) -> "TermSummary":
        et = t.enriched_term
        hr = et.harvest_record
        scheme_uri = getattr(et.taxonomy_placement, "broader_uri", None) if et.taxonomy_placement else None
        scheme_label = _last_segment(scheme_uri) if scheme_uri else None
        return cls(
            term_uri=t.term_uri,
            preferred_label=et.preferred_label or "",
            definition=et.definition or "",
            lifecycle_status=t.lifecycle_status.value,
            scheme=scheme_uri,
            scheme_label=scheme_label,
            approved_by=t.approved_by,
            version=t.version,
            source_system=hr.source_system if hr else None,
        )


class RelationOut(BaseModel):
    predicate: str
    object_label: str
    object_uri: str | None


class BusinessRuleOut(BaseModel):
    rule: str
    rule_type: str | None


class TermDetail(TermSummary):
    alt_labels: list[str]
    broader_uri: str | None
    broader_label: str | None
    business_rules: list[str]
    relations: list[RelationOut]
    document_id: str | None
    published_at: datetime | None

    @classmethod
    def from_published(cls, t) -> "TermDetail":
        et = t.enriched_term
        hr = et.harvest_record
        tp = et.taxonomy_placement
        scheme_uri = getattr(tp, "broader_uri", None) if tp else None
        scheme_label = _last_segment(scheme_uri) if scheme_uri else None

        alt_labels = [
            cl.text for cl in et.candidate_labels
            if cl.text != et.preferred_label
        ]

        relations = [
            RelationOut(
                predicate=_last_segment(r.predicate),
                object_label=r.object_label or _last_segment(r.object_uri),
                object_uri=r.object_uri,
            )
            for r in (et.relations or [])
        ]

        rules = [br.rule for br in (et.business_rules or [])]

        return cls(
            term_uri=t.term_uri,
            preferred_label=et.preferred_label or "",
            definition=et.definition or "",
            lifecycle_status=t.lifecycle_status.value,
            scheme=scheme_uri,
            scheme_label=scheme_label,
            approved_by=t.approved_by,
            version=t.version,
            source_system=hr.source_system if hr else None,
            alt_labels=alt_labels,
            broader_uri=getattr(tp, "broader_uri", None) if tp else None,
            broader_label=_last_segment(getattr(tp, "broader_uri", None)) if tp else None,
            business_rules=rules,
            relations=relations,
            document_id=hr.document_id if hr else None,
            published_at=t.published_at,
        )


class StatusTransitionRequest(BaseModel):
    new_status: str
    actor: str | None = None
    comment: str | None = None


class PipelineRunResponse(BaseModel):
    published: int
    skipped: int
    failed: int
    terms: list[TermSummary]


class AuditEntryOut(BaseModel):
    entry_id: str
    term_uri: str
    term_label: str
    action: str
    actor: str | None
    previous_status: str | None
    new_status: str | None
    timestamp: str
    comment: str | None

    @classmethod
    def from_entry(cls, e) -> "AuditEntryOut":
        return cls(
            entry_id=e.entry_id,
            term_uri=e.term_uri,
            term_label=e.term_label,
            action=e.action,
            actor=e.actor,
            previous_status=e.previous_status.value if e.previous_status else None,
            new_status=e.new_status.value if e.new_status else None,
            timestamp=e.timestamp.isoformat(),
            comment=e.comment,
        )


class StatsOut(BaseModel):
    total: int
    by_status: dict[str, int]
    by_scheme: dict[str, int]
    recent_activity: int


def _last_segment(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
