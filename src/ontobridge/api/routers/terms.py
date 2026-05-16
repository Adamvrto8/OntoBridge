from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import io

from dataclasses import replace

from ontobridge.api.deps import AuditDep, OntologyDep, PublisherDep
from ontobridge.api.schemas import StatusTransitionRequest, TermDetail, TermPatch, TermSummary
from ontobridge.agents.relations.lexicon import InverseVerbLexicon
from ontobridge.models.enrichment import CandidateLabel, SemanticRelation, TaxonomyPlacement
from ontobridge.models.enums import PlacementStatus, RelationStatus
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
def get_term(term_id: str, publisher: PublisherDep, ontology: OntologyDep):
    try:
        term = publisher.get_term(term_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Term not found")
    return TermDetail.from_published(term, ontology=ontology)


@router.patch("/{term_id:path}/edit", response_model=TermDetail)
def edit_term(
    term_id: str,
    body: TermPatch,
    publisher: PublisherDep,
    audit: AuditDep,
    ontology: OntologyDep,
):
    try:
        term = publisher.get_term(term_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Term not found")

    enriched = term.enriched_term
    changes: list[str] = []

    if body.definition is not None:
        enriched = replace(enriched, definition=body.definition.strip())
        changes.append("definition")

    if body.alt_labels is not None:
        cleaned = [l.strip() for l in body.alt_labels if l.strip()]
        existing_pref = {c.text.casefold() for c in enriched.candidate_labels if c.confidence >= 0.9}
        new_labels = [
            CandidateLabel(text=l, confidence=0.8)
            for l in cleaned
            if l.casefold() not in existing_pref
        ]
        kept_auto = [c for c in enriched.candidate_labels if c.confidence >= 0.9]
        enriched = replace(enriched, candidate_labels=kept_auto + new_labels)
        changes.append("alt_labels")

    if body.broader_concept_uri is not None:
        existing_tp = enriched.taxonomy_placement
        enriched = replace(enriched, taxonomy_placement=TaxonomyPlacement(
            broader_concept_uri=body.broader_concept_uri,
            scheme_uri=body.scheme_uri or (existing_tp.scheme_uri if existing_tp else None),
            domain_prefix=existing_tp.domain_prefix if existing_tp else None,
            placement_confidence=1.0,
            status=PlacementStatus.PLACED,
            sibling_conflicts=[],
        ))
        changes.append("taxonomy")

    if body.relations_delete is not None or body.relations_add is not None:
        relations = list(enriched.relations or [])
        if body.relations_delete:
            for idx in sorted(set(body.relations_delete), reverse=True):
                if 0 <= idx < len(relations):
                    relations.pop(idx)
        if body.relations_add:
            lexicon = InverseVerbLexicon.from_ontology(ontology)
            tp = enriched.taxonomy_placement
            subject_uri = (
                tp.domain_prefix if tp and tp.domain_prefix
                else f"_:steward/{(enriched.preferred_label or 'unknown').replace(' ', '_')}"
            )
            for rel in body.relations_add:
                verb = rel.verb.strip()
                obj  = rel.object_label.strip()
                if not verb or not obj:
                    continue
                lookup = lexicon.lookup(verb)
                if lookup:
                    relations.append(SemanticRelation(
                        subject_uri=subject_uri,
                        predicate_uri=lookup.predicate_uri,
                        object_label=obj,
                        inverse_predicate_uri=lookup.inverse_predicate_uri,
                        verb=verb,
                        confidence=1.0,
                        status=RelationStatus.RESOLVED,
                    ))
                else:
                    relations.append(SemanticRelation(
                        subject_uri=subject_uri,
                        predicate_uri=None,
                        object_label=obj,
                        inverse_predicate_uri=None,
                        verb=verb,
                        confidence=0.5,
                        status=RelationStatus.UNRESOLVED_VERB,
                    ))
        enriched = replace(enriched, relations=relations)
        changes.append("relations")

    updated_term = replace(term, enriched_term=enriched)
    saved = publisher.update_term(term_id, updated_term)

    audit.record(AuditEntry(
        term_uri=term_id,
        term_label=enriched.preferred_label or term_id,
        action="edit:" + ",".join(changes),
        actor=body.actor,
        previous_status=term.lifecycle_status,
        new_status=saved.lifecycle_status,
        comment=f"Steward edited: {', '.join(changes)}",
    ))

    return TermDetail.from_published(saved, ontology=ontology)


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
