from __future__ import annotations

import streamlit as st

from ontobridge.dashboard.context import DashboardContext
from ontobridge.models import LifecycleStatus


def render_glossary(ctx: DashboardContext) -> None:
    st.title("Glossary Browser")
    st.caption("Published terms only — what consumers see in Dawiso.")

    query = st.text_input("Search", placeholder="Filter by label or definition...")
    hits = ctx.publisher.search_terms(query) if query else ctx.publisher.search_terms("")
    published = [t for t in hits if t.lifecycle_status is LifecycleStatus.PUBLISHED]

    if not published:
        st.info(
            "No published terms yet. Approve REVIEW terms from the Governance "
            "Inbox to populate the glossary."
        )
        return

    published.sort(key=lambda t: t.enriched_term.preferred_label or "")
    st.markdown(f"**{len(published)}** published term(s)")

    for term in published:
        enriched = term.enriched_term
        with st.container(border=True):
            cols = st.columns([4, 1])
            cols[0].markdown(f"### {enriched.preferred_label}")
            if cols[1].button("Open", key=f"glossary_open_{term.term_uri}"):
                st.session_state["selected_term_uri"] = term.term_uri
                st.session_state["nav"] = "Term Detail"
                st.rerun()
            if enriched.definition:
                st.write(enriched.definition)
            alts = [c.text for c in enriched.candidate_labels if c.text != enriched.preferred_label]
            if alts:
                st.caption("Alt labels: " + ", ".join(alts))
            if term.approved_by:
                st.caption(f"Approved by {term.approved_by}")
