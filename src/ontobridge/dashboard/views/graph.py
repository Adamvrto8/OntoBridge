from __future__ import annotations

import os
import tempfile

import streamlit as st
import streamlit.components.v1 as components

from ontobridge.dashboard.context import DashboardContext
from ontobridge.models import LifecycleStatus
from ontobridge.models.published import PublishedTerm

_SCHEME_COLORS: dict[str, str] = {
    "LoanScheme": "#4a90d9",
    "RiskScheme": "#e74c3c",
    "ComplianceScheme": "#2ecc71",
    "PaymentScheme": "#f39c12",
    "AccountScheme": "#9b59b6",
    "TradingScheme": "#1abc9c",
    "CustomerScheme": "#e67e22",
}
_DEFAULT_NODE_COLOR = "#7f8c8d"
_TAXONOMY_EDGE_COLOR = "#aaaaaa"
_RELATION_EDGE_COLOR = "#f39c12"


def _scheme_color(scheme_uri: str | None) -> str:
    if not scheme_uri:
        return _DEFAULT_NODE_COLOR
    key = scheme_uri.rstrip("/").split("/")[-1]
    return _SCHEME_COLORS.get(key, _DEFAULT_NODE_COLOR)


def build_graph_data(
    terms: list[PublishedTerm],
) -> tuple[list[dict], list[dict]]:
    """Return (nodes, edges) dicts built from published terms.

    Taxonomy parent→child edges are included only when the parent URI
    belongs to another term in the list.  Semantic relation edges require
    the object label to match a known term label (case-insensitive).
    Self-loops are skipped.
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    uri_set = {t.term_uri for t in terms}
    label_to_uri: dict[str, str] = {}

    for term in terms:
        label = term.enriched_term.preferred_label or term.term_uri
        placement = term.enriched_term.taxonomy_placement
        color = _scheme_color(placement.scheme_uri if placement else None)
        definition = term.enriched_term.definition or ""
        tooltip = f"{label}\n{definition[:150]}" if definition else label

        nodes.append(
            {"id": term.term_uri, "label": label, "title": tooltip, "color": color}
        )
        label_to_uri[label.lower()] = term.term_uri

    seen_edges: set[tuple[str, str, str]] = set()

    def _add_edge(src: str, tgt: str, label: str, color: str) -> None:
        if src == tgt:
            return
        key = (src, tgt, label)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": src, "target": tgt, "label": label, "color": color})

    for term in terms:
        placement = term.enriched_term.taxonomy_placement
        if placement and placement.broader_concept_uri in uri_set:
            _add_edge(
                placement.broader_concept_uri,
                term.term_uri,
                "broader",
                _TAXONOMY_EDGE_COLOR,
            )

        for rel in term.enriched_term.relations:
            obj_uri = label_to_uri.get(rel.object_label.lower())
            if obj_uri and obj_uri in uri_set:
                _add_edge(term.term_uri, obj_uri, rel.verb, _RELATION_EDGE_COLOR)

    return nodes, edges


def render_graph(ctx: DashboardContext) -> None:
    st.title("Knowledge Graph")
    st.caption(
        "Auto-generated from published terms — taxonomy hierarchy and semantic "
        "relations. Nodes are coloured by SKOS scheme. Drag nodes to rearrange."
    )

    terms = [
        t
        for t in ctx.publisher.search_terms("")
        if t.lifecycle_status is LifecycleStatus.PUBLISHED
    ]

    if not terms:
        st.info(
            "No published terms yet. Approve terms in the Governance Inbox "
            "to see them appear here."
        )
        return

    nodes, edges = build_graph_data(terms)

    try:
        from pyvis.network import Network
    except ImportError:  # pragma: no cover
        st.error("pyvis is not installed. Run: pip install pyvis")
        return

    net = Network(
        height="600px",
        width="100%",
        bgcolor="#1a1a2e",
        font_color="white",
        directed=True,
    )
    net.set_options(
        """{
          "physics": {
            "barnesHut": {
              "gravitationalConstant": -8000,
              "centralGravity": 0.3,
              "springLength": 130
            }
          },
          "edges": {
            "smooth": {"type": "curvedCW", "roundness": 0.2},
            "font": {"size": 10, "align": "middle", "color": "#cccccc"},
            "arrows": {"to": {"enabled": true, "scaleFactor": 0.7}}
          },
          "nodes": {
            "shape": "dot",
            "font": {"size": 13, "bold": true}
          }
        }"""
    )

    for n in nodes:
        net.add_node(n["id"], label=n["label"], title=n["title"], color=n["color"], size=22)

    for e in edges:
        net.add_edge(e["source"], e["target"], label=e["label"], color=e["color"])

    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    ) as f:
        net.save_graph(f.name)
        tmp_path = f.name

    try:
        with open(tmp_path, encoding="utf-8") as f:
            html = f.read()
    finally:
        os.unlink(tmp_path)

    components.html(html, height=650, scrolling=False)

    st.divider()
    col_nodes, col_edges = st.columns(2)
    with col_nodes:
        st.caption("**Node colour = SKOS scheme**")
        for scheme, color in _SCHEME_COLORS.items():
            st.markdown(
                f'<span style="background:{color};padding:2px 8px;border-radius:3px;'
                f'color:white;font-size:0.8em;margin-right:4px">{scheme}</span>',
                unsafe_allow_html=True,
            )
    with col_edges:
        st.caption("**Edge types**")
        st.markdown(
            f'<span style="color:{_TAXONOMY_EDGE_COLOR}">━━</span> broader (taxonomy)<br/>'
            f'<span style="color:{_RELATION_EDGE_COLOR}">━━</span> semantic relation (verb label)',
            unsafe_allow_html=True,
        )
