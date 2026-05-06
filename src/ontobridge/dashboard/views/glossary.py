from __future__ import annotations

import streamlit as st

from ontobridge.dashboard.context import DashboardContext
from ontobridge.export import export_glossary_csv
from ontobridge.models import LifecycleStatus
from ontobridge.models.published import PublishedTerm

_ALL_SCHEMES = "All schemes"


def _scheme_label(term: PublishedTerm) -> str:
    placement = term.enriched_term.taxonomy_placement
    if placement and placement.scheme_uri:
        return placement.scheme_uri.rstrip("/").split("/")[-1]
    return "(unresolved)"


def render_glossary(ctx: DashboardContext) -> None:
    st.title("Glossary Browser")
    st.caption("Published terms only — the approved business glossary.")

    all_published = [
        t for t in ctx.publisher.search_terms("")
        if t.lifecycle_status is LifecycleStatus.PUBLISHED
    ]

    if not all_published:
        st.info(
            "No published terms yet. Approve REVIEW terms from the Governance "
            "Inbox to populate the glossary."
        )
        return

    # Collect available schemes from published terms
    schemes = sorted({_scheme_label(t) for t in all_published})
    scheme_options = [_ALL_SCHEMES] + schemes

    col_search, col_scheme = st.columns([3, 2])
    with col_search:
        query = st.text_input("Search", placeholder="Filter by label or definition...")
    with col_scheme:
        chosen_scheme = st.selectbox("Scheme", scheme_options, key="glossary_scheme")

    # Apply text search
    hits = ctx.publisher.search_terms(query) if query.strip() else all_published
    published = [t for t in hits if t.lifecycle_status is LifecycleStatus.PUBLISHED]

    # Apply scheme filter
    if chosen_scheme != _ALL_SCHEMES:
        published = [t for t in published if _scheme_label(t) == chosen_scheme]

    published.sort(key=lambda t: t.enriched_term.preferred_label or "")

    col_count, col_dl = st.columns([5, 1])
    col_count.markdown(f"**{len(published)}** term(s)")
    col_dl.download_button(
        label="Export CSV",
        data=export_glossary_csv(ctx.publisher),
        file_name="ontobridge_glossary.csv",
        mime="text/csv",
    )

    if not published:
        st.info("No terms match the current filters.")
        return

    for term in published:
        enriched = term.enriched_term
        with st.container(border=True):
            cols = st.columns([4, 1])
            cols[0].markdown(f"### {enriched.preferred_label}")
            if cols[1].button("Open", key=f"glossary_open_{term.term_uri}"):
                st.session_state["selected_term_uri"] = term.term_uri
                st.session_state["_nav_pending"] = "Term Detail"
                st.rerun()
            if enriched.definition:
                st.write(enriched.definition)
            scheme = _scheme_label(term)
            meta: list[str] = []
            if scheme != "(unresolved)":
                meta.append(f"Scheme: {scheme}")
            alts = [c.text for c in enriched.candidate_labels if c.text != enriched.preferred_label]
            if alts:
                meta.append("Alt: " + ", ".join(alts))
            if term.approved_by:
                meta.append(f"Approved by {term.approved_by}")
            if meta:
                st.caption("  ·  ".join(meta))
