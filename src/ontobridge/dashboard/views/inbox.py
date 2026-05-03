from __future__ import annotations

from collections import Counter, defaultdict

import streamlit as st

from ontobridge.dashboard.context import DashboardContext
from ontobridge.models import LifecycleStatus, PublishedTerm

_STATUS_ORDER: list[LifecycleStatus] = [
    LifecycleStatus.CANDIDATE,
    LifecycleStatus.DRAFT,
    LifecycleStatus.REVIEW,
    LifecycleStatus.PUBLISHED,
    LifecycleStatus.DEPRECATED,
]


def render_inbox(ctx: DashboardContext) -> None:
    st.title("Governance Inbox")
    st.caption("Terms awaiting steward action across the pipeline lifecycle.")

    terms = ctx.publisher.search_terms("")
    counts = Counter(t.lifecycle_status for t in terms)
    by_status: dict[LifecycleStatus, list[PublishedTerm]] = defaultdict(list)
    for t in terms:
        by_status[t.lifecycle_status].append(t)

    cols = st.columns(len(_STATUS_ORDER))
    for col, status in zip(cols, _STATUS_ORDER):
        col.metric(status.value.title(), counts.get(status, 0))

    st.divider()

    options = [s.value for s in _STATUS_ORDER]
    default_index = options.index(LifecycleStatus.REVIEW.value)
    chosen = st.selectbox(
        "Filter by status",
        options=options,
        index=default_index,
        key="inbox_filter",
    )
    chosen_status = LifecycleStatus(chosen)
    filtered = sorted(
        by_status.get(chosen_status, []),
        key=lambda t: t.enriched_term.preferred_label or "",
    )

    if not filtered:
        st.info(f"No terms in {chosen_status.value} status.")
        return

    st.markdown(f"**{len(filtered)}** term(s) in `{chosen_status.value}`")
    header = st.columns([3, 2, 2, 2, 1])
    header[0].markdown("**Term**")
    header[1].markdown("**Domain prefix**")
    header[2].markdown("**Recommended**")
    header[3].markdown("**Approver**")
    header[4].markdown("**Open**")

    for term in filtered:
        cols = st.columns([3, 2, 2, 2, 1])
        label = term.enriched_term.preferred_label or "(no label)"
        cols[0].write(label)
        prefix = (
            term.enriched_term.taxonomy_placement.domain_prefix
            if term.enriched_term.taxonomy_placement
            else "—"
        )
        cols[1].write(prefix or "—")
        gov = term.enriched_term.governance_result
        cols[2].write(gov.recommended_action if gov else "—")
        cols[3].write(term.approved_by or "—")
        if cols[4].button("Open", key=f"open_{term.term_uri}"):
            st.session_state["selected_term_uri"] = term.term_uri
            st.session_state["nav"] = "Term Detail"
            st.rerun()
