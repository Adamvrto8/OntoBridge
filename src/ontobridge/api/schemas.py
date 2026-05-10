from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

_SEV_ORDER = {"block": 0, "warn": 1, "info": 2}
_ACTION_TO_SEVERITY = {"block": "crit", "draft": "high", "review": "med", "publish": "low"}


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
    # Governance-derived fields
    severity: str           # crit / high / med / low
    confidence: float       # 0.0–1.0  (pass-rate of governance rules)
    issue_type: str | None  # e.g. "Naming · Duplicate prefLabel"
    issue_rule: str | None  # e.g. "GOV-002 · exact_label_match"
    harvested_at: str | None  # ISO timestamp for age display

    @classmethod
    def from_published(cls, t) -> "TermSummary":
        et = t.enriched_term
        hr = et.harvest_record
        tp = et.taxonomy_placement
        scheme_uri  = tp.broader_concept_uri if tp else None
        scheme_label = _last_segment(scheme_uri) if scheme_uri else None
        sr = hr.source_ref if hr else None
        gov = et.governance_result

        # Severity — from governance recommended_action
        action   = gov.recommended_action if gov else "publish"
        severity = _ACTION_TO_SEVERITY.get(action, "low")

        # Confidence — fraction of rules that did NOT trigger
        if gov and gov.findings:
            passed     = sum(1 for f in gov.findings if not f.triggered)
            confidence = round(passed / len(gov.findings), 2)
        else:
            confidence = 1.0

        # Most severe triggered finding → issue type + rule label
        issue_type = issue_rule = None
        if gov:
            triggered = sorted(
                [f for f in gov.findings if f.triggered],
                key=lambda f: (_SEV_ORDER.get(f.severity.value if hasattr(f.severity, 'value') else str(f.severity), 3), f.rule_id),
            )
            if triggered:
                top = triggered[0]
                issue_type = f"{top.category} · {top.title}"
                issue_rule = f"GOV-{top.rule_id:03d} · {top.message[:60]}"

        harvested_at = t.published_at.isoformat() if t.published_at else None

        return cls(
            term_uri=t.term_uri,
            preferred_label=et.preferred_label or "",
            definition=et.definition or "",
            lifecycle_status=t.lifecycle_status.value,
            scheme=scheme_uri,
            scheme_label=scheme_label,
            approved_by=t.approved_by,
            version=t.version,
            source_system=sr.source_system if sr else None,
            severity=severity,
            confidence=confidence,
            issue_type=issue_type,
            issue_rule=issue_rule,
            harvested_at=harvested_at,
        )


class RelationOut(BaseModel):
    predicate: str
    object_label: str
    object_uri: str | None


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
        scheme_uri   = tp.broader_concept_uri if tp else None
        scheme_label = _last_segment(scheme_uri) if scheme_uri else None
        sr  = hr.source_ref if hr else None
        gov = et.governance_result

        action   = gov.recommended_action if gov else "publish"
        severity = _ACTION_TO_SEVERITY.get(action, "low")

        if gov and gov.findings:
            passed     = sum(1 for f in gov.findings if not f.triggered)
            confidence = round(passed / len(gov.findings), 2)
        else:
            confidence = 1.0

        issue_type = issue_rule = None
        if gov:
            triggered = sorted(
                [f for f in gov.findings if f.triggered],
                key=lambda f: (_SEV_ORDER.get(f.severity.value if hasattr(f.severity, 'value') else str(f.severity), 3), f.rule_id),
            )
            if triggered:
                top = triggered[0]
                issue_type = f"{top.category} · {top.title}"
                issue_rule = f"GOV-{top.rule_id:03d} · {top.message[:60]}"

        alt_labels = [
            cl.text for cl in et.candidate_labels
            if cl.text != et.preferred_label
        ]

        relations = [
            RelationOut(
                predicate=_last_segment(r.predicate_uri) or r.predicate_uri or getattr(r, "verb", None) or "—",
                object_label=r.object_label or "—",
                object_uri=getattr(r, "object_uri", None),
            )
            for r in (et.relations or [])
            if r.object_label
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
            source_system=sr.source_system if sr else None,
            severity=severity,
            confidence=confidence,
            issue_type=issue_type,
            issue_rule=issue_rule,
            harvested_at=t.published_at.isoformat() if t.published_at else None,
            alt_labels=alt_labels,
            broader_uri=tp.broader_concept_uri if tp else None,
            broader_label=_last_segment(tp.broader_concept_uri) if tp else None,
            business_rules=rules,
            relations=relations,
            document_id=sr.document_id if sr else None,
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
