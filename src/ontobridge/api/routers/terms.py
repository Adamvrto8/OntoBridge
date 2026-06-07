from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
import io

from dataclasses import replace

from ontobridge.api.deps import AuditDep, FeedbackStoreDep, OntologyDep, PublisherDep
from ontobridge.feedback.models import FeedbackEvent
from ontobridge.api.schemas import PagedResponse, RelationActionRequest, StatusTransitionRequest, TermDetail, TermPatch, TermSummary
from ontobridge.agents.relations.lexicon import InverseVerbLexicon
from ontobridge.models.enrichment import CandidateLabel, SemanticRelation, TaxonomyPlacement
from ontobridge.models.enums import PlacementStatus, RelationStatus
from ontobridge.audit.models import AuditEntry
from ontobridge.export import export_glossary_csv, export_turtle
from ontobridge.models.enums import LifecycleStatus
from ontobridge import webhook
from ontobridge.integrations import dawiso as dawiso_integration

router = APIRouter(prefix="/terms", tags=["terms"])

_STATUS_MAP = {s.value: s for s in LifecycleStatus}


_MAX_LIMIT = 500


@router.get("", response_model=PagedResponse[TermSummary])
def list_terms(
    publisher: PublisherDep,
    search: str = "",
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    limit = max(1, min(limit, _MAX_LIMIT))
    offset = max(0, offset)
    terms = publisher.search_terms(search)
    if status:
        target = _STATUS_MAP.get(status)
        if target:
            terms = [t for t in terms if t.lifecycle_status is target]
    total = len(terms)
    page = terms[offset: offset + limit]
    return PagedResponse(
        items=[TermSummary.from_published(t) for t in page],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/export/csv")
def export_csv(publisher: PublisherDep, status: str | None = None):
    statuses = [_STATUS_MAP[status]] if status and status in _STATUS_MAP else None
    csv_text = export_glossary_csv(publisher, statuses=statuses)
    return StreamingResponse(
        io.StringIO(csv_text),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=glossary.csv"},
    )


@router.get("/export/turtle")
def export_turtle_endpoint(publisher: PublisherDep, status: str | None = None):
    """Export all terms as a single merged SKOS/OWL Turtle file.

    ?status=published          — only published terms (default)
    ?status=published,review   — comma-separated list of statuses
    ?status=all                — every term regardless of status
    """
    if status == "all":
        statuses = set(LifecycleStatus)
    elif status:
        statuses = {_STATUS_MAP[s.strip()] for s in status.split(",") if s.strip() in _STATUS_MAP} or None
    else:
        statuses = None  # export_turtle defaults to {PUBLISHED}

    ttl = export_turtle(publisher, statuses=statuses)
    return StreamingResponse(
        io.StringIO(ttl),
        media_type="text/turtle",
        headers={"Content-Disposition": 'attachment; filename="ontology.ttl"'},
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
    feedback: FeedbackStoreDep,
    ontology: OntologyDep,
):
    try:
        term = publisher.get_term(term_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Term not found")

    enriched = term.enriched_term
    changes: list[str] = []

    if body.definition is not None:
        old_definition = enriched.definition or ""
        new_definition = body.definition.strip()
        if old_definition and old_definition != new_definition:
            feedback.record(FeedbackEvent(
                event_type="definition_corrected",
                term_uri=term_id,
                term_label=enriched.preferred_label or term_id,
                old_value=old_definition,
                new_value=new_definition,
                actor=body.actor,
            ))
        enriched = replace(enriched, definition=new_definition)
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
        old_broader = existing_tp.broader_concept_uri if existing_tp else None
        if old_broader and old_broader != body.broader_concept_uri:
            feedback.record(FeedbackEvent(
                event_type="taxonomy_corrected",
                term_uri=term_id,
                term_label=enriched.preferred_label or term_id,
                old_value=old_broader,
                new_value=body.broader_concept_uri,
                actor=body.actor,
            ))
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
    background_tasks: BackgroundTasks,
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

    et = updated.enriched_term
    tp = et.taxonomy_placement
    fibo = et.fibo_match
    webhook.fire(
        event="term.published" if new_status is LifecycleStatus.PUBLISHED else "term.status_changed",
        term_uri=term_id,
        term_label=et.preferred_label or term_id,
        new_status=new_status.value,
        definition=et.definition,
        scheme=tp.scheme_uri.rstrip("/").rsplit("/", 1)[-1] if tp and tp.scheme_uri else None,
        approved_by=body.actor,
        alt_labels=[c.text for c in et.candidate_labels if c.text != et.preferred_label],
        fibo_uri=fibo.uri if fibo else None,
    )

    # Publish to Dawiso when term is approved — fire-and-forget, never blocks response
    if new_status is LifecycleStatus.PUBLISHED:
        dawiso = dawiso_integration.get_publisher()
        if dawiso:
            background_tasks.add_task(dawiso.publish, updated)

    return TermSummary.from_published(updated)


@router.post("/{term_id:path}/publish-dawiso")
def publish_term_to_dawiso(term_id: str, publisher: PublisherDep):
    """Manually trigger Dawiso publish for an already-approved term.

    Useful for re-syncing or triggering from the MCP server.
    Returns {"dawiso_url": "..."} on success.
    """
    try:
        term = publisher.get_term(term_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Term not found")

    if term.lifecycle_status is not LifecycleStatus.PUBLISHED:
        raise HTTPException(status_code=422, detail="Term must be in PUBLISHED status")

    dawiso = dawiso_integration.get_publisher()
    if not dawiso:
        raise HTTPException(status_code=503, detail="Dawiso integration not configured (set DAWISO_URL and DAWISO_TOKEN)")

    url = dawiso.publish(term)
    return {"dawiso_url": url or "", "term_uri": term_id, "label": term.enriched_term.preferred_label}


@router.patch("/{term_id:path}/relations", response_model=TermDetail)
def update_relation(
    term_id: str,
    body: RelationActionRequest,
    publisher: PublisherDep,
    feedback: FeedbackStoreDep,
):
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="action must be 'approve' or 'reject'")
    try:
        term = publisher.get_term(term_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Term not found")

    et = term.enriched_term
    relation_desc = f"{body.verb} → {body.object_label}"
    for i, r in enumerate(et.relations):
        if r.verb == body.verb and r.object_label == body.object_label and r.status == RelationStatus.PROPOSED:
            if body.action == "reject":
                et.relations.pop(i)
                feedback.record(FeedbackEvent(
                    event_type="relation_rejected",
                    term_uri=term_id,
                    term_label=et.preferred_label or term_id,
                    old_value=relation_desc,
                    new_value="",
                    actor=getattr(body, "actor", "steward"),
                ))
            else:
                new_status = (
                    RelationStatus.RESOLVED
                    if r.predicate_uri and r.inverse_predicate_uri
                    else RelationStatus.CONFIRMED
                )
                r.status = new_status
                feedback.record(FeedbackEvent(
                    event_type="relation_approved",
                    term_uri=term_id,
                    term_label=et.preferred_label or term_id,
                    old_value="",
                    new_value=relation_desc,
                    actor=getattr(body, "actor", "steward"),
                ))
            break
    else:
        raise HTTPException(status_code=404, detail="Proposed relation not found")

    try:
        updated = publisher.update_term(term_id, term)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    return TermDetail.from_published(updated)
