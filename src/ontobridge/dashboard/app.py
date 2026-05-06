from __future__ import annotations

import streamlit as st

from ontobridge.dashboard.config import DashboardConfig
from ontobridge.audit import AuditLog, InMemoryAuditLog
from ontobridge.dashboard.context import DashboardContext
from ontobridge.dashboard.seed import build_sample_publisher, load_ontology
from ontobridge.models.enums import LifecycleStatus
from ontobridge.publisher.base import TermPublisher
from ontobridge.dashboard.views import (
    render_audit,
    render_detail,
    render_glossary,
    render_graph,
    render_inbox,
    render_miro,
    render_stats,
)

_PAGES = {
    "Governance Inbox": render_inbox,
    "Term Detail": render_detail,
    "Glossary Browser": render_glossary,
    "Pipeline Stats": render_stats,
    "Knowledge Graph": render_graph,
    "Audit Log": render_audit,
    "Miro Board": render_miro,
}


@st.cache_resource
def _load_ontology(path_str: str):
    return load_ontology(path_str)


@st.cache_resource
def _load_in_memory_publisher(_ontology):
    # Underscore prefix excludes _ontology from cache hashing.
    return build_sample_publisher(_ontology)


@st.cache_resource
def _load_sqlite_publisher(db_path_str: str, _ontology):
    # Underscore prefix excludes _ontology from cache hashing.
    from ontobridge.publisher import SqlitePublisher
    pub = SqlitePublisher(db_path_str)
    if pub.count() == 0:
        # First launch: seed with sample terms so the dashboard is not empty.
        seeded = build_sample_publisher(_ontology)
        for term in seeded.search_terms(""):
            pub.create_term(term)
    return pub


@st.cache_resource
def _load_in_memory_audit() -> AuditLog:
    return InMemoryAuditLog()


@st.cache_resource
def _load_sqlite_audit(audit_path_str: str) -> AuditLog:
    from ontobridge.audit import SqliteAuditLog
    return SqliteAuditLog(audit_path_str)


def sidebar_counts(publisher: TermPublisher, audit_log: AuditLog) -> dict[str, int]:
    """Return a {page_name: count} dict for pages where a badge is meaningful."""
    terms = publisher.search_terms("")
    review = sum(1 for t in terms if t.lifecycle_status is LifecycleStatus.REVIEW)
    published = sum(1 for t in terms if t.lifecycle_status is LifecycleStatus.PUBLISHED)
    audit = audit_log.count()
    counts: dict[str, int] = {}
    if review:
        counts["Governance Inbox"] = review
    if published:
        counts["Glossary Browser"] = published
    if audit:
        counts["Audit Log"] = audit
    return counts


def main(config: DashboardConfig | None = None) -> None:
    cfg = config or DashboardConfig()
    st.set_page_config(
        page_title=cfg.page_title,
        page_icon=cfg.page_icon,
        layout="wide",
    )

    ontology = _load_ontology(str(cfg.ontology_path))

    if cfg.db_path is not None:
        publisher = _load_sqlite_publisher(str(cfg.db_path), ontology)
        audit_path = cfg.db_path.with_stem(cfg.db_path.stem + "_audit")
        audit_log: AuditLog = _load_sqlite_audit(str(audit_path))
        persistent = True
    else:
        publisher = _load_in_memory_publisher(ontology)
        audit_log = _load_in_memory_audit()
        persistent = False

    ctx = DashboardContext(
        publisher=publisher, ontology=ontology, config=cfg, audit_log=audit_log
    )

    # Apply any pending navigation set by a view before the radio widget reads state.
    if "_nav_pending" in st.session_state:
        st.session_state["nav"] = st.session_state.pop("_nav_pending")

    counts = sidebar_counts(publisher, audit_log)

    def _label(page: str) -> str:
        n = counts.get(page, 0)
        return f"{page}  ({n})" if n else page

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
            format_func=_label,
        )
        st.divider()

        if persistent:
            st.caption(f"Storage: SQLite — `{cfg.db_path.name}`")  # type: ignore[union-attr]
        else:
            st.caption("Storage: in-memory (demo)")
            if st.button("Reset publisher (re-seed)"):
                _load_in_memory_publisher.clear()  # type: ignore[attr-defined]
                st.session_state.pop("selected_term_uri", None)
                st.rerun()

        st.caption(f"Ontology: `{cfg.ontology_path.name}`")

    _PAGES[nav](ctx)


if __name__ == "__main__":  # pragma: no cover - streamlit invokes via run
    main()
