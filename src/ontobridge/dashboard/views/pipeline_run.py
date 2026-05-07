from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from ontobridge.batch import BatchPipelineRunner
from ontobridge.dashboard.context import DashboardContext

_ACCEPTED_TYPES = ["txt", "pdf", "docx", "csv"]


def render_pipeline_run(ctx: DashboardContext) -> None:
    st.title("Run Pipeline")
    st.caption("Upload a document, extract business terms and push them through the pipeline.")

    uploaded = st.file_uploader(
        "Upload document",
        type=_ACCEPTED_TYPES,
        help="Supported formats: plain text (.txt), PDF, Word (.docx), CSV catalog.",
    )

    col_sys, col_user = st.columns(2)
    source_system = col_sys.text_input(
        "Source system", value="upload", key="run_source_system"
    )
    approved_by = col_user.text_input(
        "Approved by (optional)", value="", key="run_approved_by"
    )

    if st.button("Run Pipeline", disabled=uploaded is None, type="primary"):
        _run(
            ctx,
            uploaded,
            source_system=source_system or "upload",
            approved_by=approved_by.strip() or None,
        )


def _run(ctx: DashboardContext, uploaded, *, source_system: str, approved_by: str | None) -> None:
    progress_bar = st.progress(0, text="Starting pipeline…")

    suffix = Path(uploaded.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.read())
        tmp_path = Path(tmp.name)

    try:
        runner = BatchPipelineRunner(
            ontology=ctx.ontology,
            publisher=ctx.publisher,
            on_progress=lambda done, total: progress_bar.progress(
                done / total,
                text=f"Processing term {done} / {total}…",
            ),
        )
        result = runner.run_document(
            tmp_path,
            source_system=source_system,
            document_id=uploaded.name,
            approved_by=approved_by,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    progress_bar.progress(1.0, text="Done.")

    col_pub, col_skip, col_fail = st.columns(3)
    col_pub.metric("Published", len(result.published))
    col_skip.metric("Skipped", len(result.skipped))
    col_fail.metric("Failed", len(result.failed))

    if not result.total:
        st.warning(
            "No terms were extracted from the document. "
            "Check that the file contains business term definitions."
        )
        return

    if result.published:
        st.success(f"{len(result.published)} term(s) added to the pipeline.")
        if st.button("Open Governance Inbox"):
            st.session_state["_nav_pending"] = "Governance Inbox"
            st.rerun()

    if result.skipped:
        with st.expander(f"Skipped ({len(result.skipped)})"):
            for term, reason in result.skipped:
                label = term.preferred_label or "(unlabelled)"
                st.markdown(f"- **{label}**: {reason}")

    if result.failed:
        with st.expander(f"Failed ({len(result.failed)})", expanded=True):
            for ft in result.failed:
                label = ft.term.preferred_label or "(unlabelled)"
                st.markdown(f"- **{label}** `{ft.error_type}`: {ft.error}")
