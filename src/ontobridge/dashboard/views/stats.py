from __future__ import annotations

from collections import Counter

import streamlit as st

from ontobridge.dashboard.context import DashboardContext
from ontobridge.models import LifecycleStatus


def render_stats(ctx: DashboardContext) -> None:
    st.title("Pipeline Stats")
    st.caption("Snapshot of the current publisher state.")

    terms = ctx.publisher.search_terms("")
    if not terms:
        st.info("Publisher is empty.")
        return

    # Lifecycle counts
    status_counts = Counter(t.lifecycle_status.value for t in terms)
    cols = st.columns(len(LifecycleStatus))
    for col, status in zip(cols, list(LifecycleStatus)):
        col.metric(status.value.title(), status_counts.get(status.value, 0))

    st.divider()

    # Governance pass rate
    governed = [t for t in terms if t.enriched_term.governance_result is not None]
    if governed:
        passed = sum(
            1 for t in governed
            if t.enriched_term.governance_result.recommended_action == "publish"
        )
        rate = passed / len(governed)
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Governance pass rate", f"{rate:.0%}")
        col_b.metric("Passed", passed)
        col_c.metric("Total governed", len(governed))

    st.divider()

    # By scheme
    st.subheader("Terms per scheme")
    scheme_counts: Counter[str] = Counter()
    for t in terms:
        placement = t.enriched_term.taxonomy_placement
        if placement is None or placement.scheme_uri is None:
            scheme_counts["(unresolved)"] += 1
            continue
        label = ctx.ontology.scheme_label(placement.scheme_uri) or placement.scheme_uri
        scheme_counts[label] += 1
    if scheme_counts:
        st.bar_chart(dict(scheme_counts))

    st.divider()

    # Recommended-action distribution
    st.subheader("Governance recommended actions")
    action_counts = Counter(
        t.enriched_term.governance_result.recommended_action
        for t in terms
        if t.enriched_term.governance_result is not None
    )
    if action_counts:
        st.bar_chart(dict(action_counts))
