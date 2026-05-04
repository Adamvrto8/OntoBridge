from __future__ import annotations

import streamlit as st

from ontobridge.dashboard.config import DashboardConfig
from ontobridge.dashboard.context import DashboardContext
from ontobridge.dashboard.seed import build_sample_publisher, load_ontology
from ontobridge.dashboard.views import (
    render_detail,
    render_glossary,
    render_inbox,
    render_miro,
    render_stats,
)

_PAGES = {
    "Governance Inbox": render_inbox,
    "Term Detail": render_detail,
    "Glossary Browser": render_glossary,
    "Pipeline Stats": render_stats,
    "Miro Board": render_miro,
}


@st.cache_resource
def _load_ontology(path_str: str):
    return load_ontology(path_str)


@st.cache_resource
def _load_publisher(_ontology):
    # Underscore-prefixed args are excluded from cache hashing — we want a
    # single shared publisher per session, mutated in place by the views.
    return build_sample_publisher(_ontology)


def main(config: DashboardConfig | None = None) -> None:
    cfg = config or DashboardConfig()
    st.set_page_config(
        page_title=cfg.page_title,
        page_icon=cfg.page_icon,
        layout="wide",
    )

    ontology = _load_ontology(str(cfg.ontology_path))
    publisher = _load_publisher(ontology)
    ctx = DashboardContext(publisher=publisher, ontology=ontology, config=cfg)

    # Apply any pending navigation set by a view before the radio widget reads state.
    if "_nav_pending" in st.session_state:
        st.session_state["nav"] = st.session_state.pop("_nav_pending")

    with st.sidebar:
        st.title("OntoBridge")
        st.caption("Steward Dashboard")
        nav = st.radio(
            "Navigate",
            list(_PAGES.keys()),
            key="nav",
            index=list(_PAGES.keys()).index(
                st.session_state.get("nav", "Governance Inbox")
            ),
        )
        st.divider()
        if st.button("Reset publisher (re-seed)"):
            _load_publisher.clear()  # type: ignore[attr-defined]
            st.session_state.pop("selected_term_uri", None)
            st.rerun()
        st.caption(f"Ontology: `{cfg.ontology_path.name}`")

    _PAGES[nav](ctx)


if __name__ == "__main__":  # pragma: no cover - streamlit invokes via run
    main()
