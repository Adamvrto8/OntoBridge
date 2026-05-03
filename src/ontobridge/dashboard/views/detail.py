from __future__ import annotations

from dataclasses import replace

import streamlit as st

from ontobridge.dashboard.context import DashboardContext
from ontobridge.models import LifecycleStatus, RelationStatus
from ontobridge.models.enums import PlacementStatus

_SEVERITY_ICON = {
    "info": "🟢",
    "warn": "🟡",
    "block": "🔴",
}
_LIFECYCLE_BADGE = {
    LifecycleStatus.CANDIDATE: "🟧 candidate",
    LifecycleStatus.DRAFT: "🟦 draft",
    LifecycleStatus.REVIEW: "🟨 review",
    LifecycleStatus.PUBLISHED: "🟩 published",
    LifecycleStatus.DEPRECATED: "⬛ deprecated",
}


def render_detail(ctx: DashboardContext) -> None:
    uri = st.session_state.get("selected_term_uri")
    if not uri:
        st.title("Term Detail")
        st.info("Open a term from the Governance Inbox to see its detail view.")
        return

    try:
        term = ctx.publisher.get_term(uri)
    except KeyError:
        st.error(f"Term {uri!r} no longer exists in the publisher.")
        st.session_state.pop("selected_term_uri", None)
        return

    enriched = term.enriched_term
    label = enriched.preferred_label or "(no label)"

    st.title(label)
    st.markdown(
        f"`{term.term_uri}` · {_LIFECYCLE_BADGE.get(term.lifecycle_status, term.lifecycle_status.value)} · v{term.version}"
    )

    _render_breadcrumb(ctx, enriched)
    _render_labels_and_definition(enriched)
    _render_relations(enriched)
    _render_provenance(enriched)
    _render_governance(enriched)
    _render_turtle(term)
    _render_actions(ctx, term)


def _render_breadcrumb(ctx: DashboardContext, enriched) -> None:
    placement = enriched.taxonomy_placement
    if placement is None:
        return
    st.subheader("Taxonomy")
    parts: list[str] = []
    if placement.scheme_uri:
        scheme_label = ctx.ontology.scheme_label(placement.scheme_uri) or placement.scheme_uri
        parts.append(scheme_label)
    if placement.broader_concept_uri:
        broader = ctx.ontology.by_uri(placement.broader_concept_uri)
        parts.append(broader.pref_label if broader else placement.broader_concept_uri)
    parts.append(enriched.preferred_label or "—")
    st.markdown(" › ".join(f"**{p}**" for p in parts))
    if placement.domain_prefix:
        st.caption(f"Proposed CURIE: `{placement.domain_prefix}`")
    if placement.status is PlacementStatus.UNRESOLVED:
        st.warning("Placement is **unresolved** — confidence below threshold.")
    if placement.sibling_conflicts:
        with st.expander(f"⚠️ {len(placement.sibling_conflicts)} sibling conflict(s)"):
            for sc in placement.sibling_conflicts:
                st.markdown(
                    f"- `{sc.sibling_label}` ({sc.similarity:.2f} similar) — `{sc.sibling_uri}`"
                )


def _render_labels_and_definition(enriched) -> None:
    st.subheader("Labels & definition")
    pref = enriched.preferred_label or "—"
    alts = [c.text for c in enriched.candidate_labels if c.text != enriched.preferred_label]
    st.markdown(f"**Preferred label:** {pref}")
    if alts:
        st.markdown("**Alt labels:** " + ", ".join(f"`{a}`" for a in alts))
    if enriched.definition:
        st.markdown("**Definition**")
        st.write(enriched.definition)
    else:
        st.info("No definition recorded.")


def _render_relations(enriched) -> None:
    if not enriched.relations:
        return
    st.subheader("Semantic relations")
    for rel in enriched.relations:
        if rel.status is RelationStatus.RESOLVED:
            pred = rel.predicate_uri.rsplit("/", 1)[-1] if rel.predicate_uri else "?"
            inv = (
                rel.inverse_predicate_uri.rsplit("/", 1)[-1]
                if rel.inverse_predicate_uri
                else "?"
            )
            st.markdown(
                f"🟢 **{rel.verb}** · `{pred}` ↔ `{inv}`  →  *{rel.object_label}*"
            )
        else:
            st.markdown(
                f"🟡 **{rel.verb}** *(unresolved verb — needs steward review)* "
                f" →  *{rel.object_label}*"
            )


def _render_provenance(enriched) -> None:
    if not enriched.policy_context:
        return
    st.subheader("Provenance")
    for ctx in enriched.policy_context:
        ref = ctx.document_ref + (f"#{ctx.section}" if ctx.section else "")
        st.markdown(f"- `{ref}`")
        if ctx.paragraph:
            st.caption(ctx.paragraph)


def _render_governance(enriched) -> None:
    gov = enriched.governance_result
    if gov is None:
        return
    st.subheader("Governance")
    st.markdown(
        f"**Recommended action:** `{gov.recommended_action}` · "
        f"**Blocking flags:** {', '.join(gov.blocking_flags) if gov.blocking_flags else 'none'}"
    )
    for finding in gov.findings:
        icon = _SEVERITY_ICON.get(finding.severity.value, "⚪")
        triggered = "⚠️ triggered" if finding.triggered else "✓ ok"
        st.markdown(
            f"{icon} **R{finding.rule_id:02d}** · {finding.category} · {finding.title} — *{triggered}*"
        )
        if finding.triggered and finding.message:
            st.caption(finding.message)


def _render_turtle(term) -> None:
    if not term.turtle:
        return
    with st.expander("Turtle (.ttl) serialization"):
        st.code(term.turtle, language="turtle")


def _render_actions(ctx: DashboardContext, term) -> None:
    st.subheader("Actions")
    cols = st.columns([2, 1, 1, 1])
    approver_input = cols[0].text_input(
        "Approver name",
        value=term.approved_by or "",
        key=f"approver_{term.term_uri}",
        help="Required to approve into PUBLISHED.",
    )
    approve = cols[1].button("Approve", key=f"approve_{term.term_uri}", type="primary")
    send_draft = cols[2].button("Send to draft", key=f"draft_{term.term_uri}")
    reject = cols[3].button("Reject", key=f"reject_{term.term_uri}")

    if approve:
        if not approver_input.strip():
            st.error("Enter an approver name before approving.")
        else:
            _attempt_approve(ctx, term, approver_input.strip())
    elif send_draft:
        _attempt_transition(ctx, term, LifecycleStatus.DRAFT)
    elif reject:
        _attempt_transition(ctx, term, LifecycleStatus.CANDIDATE)


def _attempt_transition(ctx: DashboardContext, term, target: LifecycleStatus) -> None:
    try:
        if target is LifecycleStatus.PUBLISHED:
            raise ValueError("Use Approve to publish.")
        ctx.publisher.transition_status(term.term_uri, target)
        st.success(f"Transitioned to {target.value}.")
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))


def _attempt_approve(ctx: DashboardContext, term, approver: str) -> None:
    try:
        current = ctx.publisher.get_term(term.term_uri)
        # PUBLISHED requires approved_by; persist it before transitioning.
        if current.lifecycle_status is LifecycleStatus.CANDIDATE:
            ctx.publisher.transition_status(term.term_uri, LifecycleStatus.REVIEW)
            current = ctx.publisher.get_term(term.term_uri)
        ctx.publisher.update_term(
            term.term_uri,
            replace(current, approved_by=approver),
        )
        ctx.publisher.transition_status(term.term_uri, LifecycleStatus.PUBLISHED)
        st.success(f"Approved by {approver} — now PUBLISHED.")
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))
