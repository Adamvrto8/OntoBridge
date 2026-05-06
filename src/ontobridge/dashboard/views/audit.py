from __future__ import annotations

import streamlit as st

from ontobridge.dashboard.context import DashboardContext

_ACTION_ICON = {
    "approved": "✅",
    "rejected": "❌",
    "sent_to_draft": "📝",
    "sent_to_review": "🔍",
}


def render_audit(ctx: DashboardContext) -> None:
    st.title("Audit Log")
    col_title, col_btn = st.columns([6, 1])
    col_title.caption("Every approve, reject, and status transition recorded by stewards.")
    if col_btn.button("Refresh", key="audit_refresh"):
        st.rerun()

    total = ctx.audit_log.count()

    if total == 0:
        st.info(
            "No audit entries yet. Approve or reject terms in the Term Detail "
            "view to start recording actions here."
        )
        return

    col_filter, col_actor = st.columns(2)
    with col_filter:
        term_filter = st.text_input("Filter by term label (partial)", key="audit_term_filter")
    with col_actor:
        actor_filter = st.text_input("Filter by actor name (partial)", key="audit_actor_filter")

    entries = ctx.audit_log.entries(limit=200)

    if term_filter.strip():
        entries = [e for e in entries if term_filter.lower() in e.term_label.lower()]
    if actor_filter.strip():
        entries = [e for e in entries if actor_filter.lower() in e.actor.lower()]

    st.markdown(f"**{len(entries)}** entr{'y' if len(entries) == 1 else 'ies'} (newest first)")

    header = st.columns([1, 3, 2, 2, 2, 2])
    header[0].markdown("**Action**")
    header[1].markdown("**Term**")
    header[2].markdown("**Actor**")
    header[3].markdown("**From**")
    header[4].markdown("**To**")
    header[5].markdown("**When**")

    for entry in entries:
        cols = st.columns([1, 3, 2, 2, 2, 2])
        icon = _ACTION_ICON.get(entry.action, "•")
        cols[0].write(f"{icon} {entry.action}")
        cols[1].write(entry.term_label)
        cols[2].write(entry.actor)
        cols[3].write(entry.previous_status.value)
        cols[4].write(entry.new_status.value)
        cols[5].write(entry.timestamp.strftime("%Y-%m-%d %H:%M"))
