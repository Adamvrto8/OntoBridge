from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PagedResponse(BaseModel, Generic[T]):
    """Standard paginated envelope returned by all list endpoints."""
    items: list[T]
    total: int
    limit: int
    offset: int

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
        scheme_uri   = tp.scheme_uri if tp else None
        scheme_label = _resolve_scheme_label(scheme_uri, None)
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
    verb: str
    object_label: str
    object_uri: str | None
    status: str   # resolved | confirmed | proposed | unresolved_verb | fibo_match
    source: str | None  # fibo | llm | svo


class TermDetail(TermSummary):
    alt_labels: list[str]
    broader_uri: str | None
    broader_label: str | None
    ancestor_path: list[str] = []
    business_rules: list[str]
    relations: list[RelationOut]
    document_id: str | None
    published_at: datetime | None
    fibo_uri: str | None
    fibo_match_type: str | None
    definition_source: str  # "document" | "fibo" | "llm"
    fibo_suggested_definition: str | None  # FIBO expected_definition, always included when available

    @classmethod
    def from_published(cls, t, ontology=None) -> "TermDetail":
        et = t.enriched_term
        hr = et.harvest_record
        tp = et.taxonomy_placement
        scheme_uri   = tp.scheme_uri if tp else None
        scheme_label = _resolve_scheme_label(scheme_uri, ontology)
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
                verb=getattr(r, "verb", None) or "—",
                object_label=r.object_label or "—",
                object_uri=getattr(r, "object_uri", None),
                status=r.status.value if hasattr(r.status, "value") else str(r.status),
                source=getattr(r, "source", None),
            )
            for r in (et.relations or [])
            if r.object_label
        ]

        rules = [br.rule_text for br in (et.business_rules or [])]

        fibo = et.fibo_match
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
            ancestor_path=_build_ancestor_path(tp.broader_concept_uri if tp else None, ontology),
            business_rules=rules,
            relations=relations,
            document_id=sr.document_id if sr else None,
            published_at=t.published_at,
            fibo_uri=fibo.uri if fibo else None,
            fibo_match_type=fibo.match_type if fibo else None,
            definition_source=et.definition_source,
            fibo_suggested_definition=fibo.expected_definition if fibo else None,
        )


class StatusTransitionRequest(BaseModel):
    new_status: str
    actor: str | None = None
    comment: str | None = None


class RelationActionRequest(BaseModel):
    verb: str
    object_label: str
    action: str  # "approve" | "reject"


class PipelineRunResponse(BaseModel):
    published: int
    merged: int = 0
    drifted: int = 0
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
    with_definition: int


class RelationAdd(BaseModel):
    verb: str
    object_label: str


class TermPatch(BaseModel):
    """Fields a steward can edit on an existing term. All fields are optional —
    only those present in the request body are applied."""
    definition: str | None = None
    alt_labels: list[str] | None = None
    broader_concept_uri: str | None = None
    scheme_uri: str | None = None
    relations_delete: list[int] | None = None
    relations_add: list[RelationAdd] | None = None
    actor: str | None = None


class OntologyConceptOut(BaseModel):
    uri: str
    pref_label: str
    scheme_uri: str | None
    scheme_label: str | None


def _resolve_scheme_label(scheme_uri: str | None, ontology) -> str | None:
    if not scheme_uri:
        return None
    if ontology is not None:
        label = ontology.scheme_label(scheme_uri)
        if label:
            return label.split("@")[0].strip()  # strip lang tag if present
    seg = _last_segment(scheme_uri) or ""
    return seg.removeprefix("Scheme") or seg or None


def _build_ancestor_path(broader_uri: str | None, ontology) -> list[str]:
    if not broader_uri or ontology is None:
        return []
    path: list[str] = []
    current = broader_uri
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        concept = ontology.by_uri(current)
        if concept is None:
            break
        path.append(concept.pref_label)
        current = ontology.get_broader(current)
    return list(reversed(path))


def _last_segment(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
