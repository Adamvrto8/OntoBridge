from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from ontobridge.agents.harvester.agent import HarvesterAgent
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

    st.divider()

    col_ner, col_def = st.columns(2)
    use_llm_ner = col_ner.toggle(
        "Use LLM extractor",
        value=False,
        key="run_use_llm_ner",
        help="Uses an LLM to extract terms from natural prose. Works on any document, not just formal glossaries.",
    )
    use_llm_def = col_def.toggle(
        "Improve definitions with LLM",
        value=False,
        key="run_use_llm_def",
        help="After taxonomy placement, an LLM rewrites each definition and generates IF...THEN business rules.",
    )

    llm_backend = None
    llm_model = None
    if use_llm_ner or use_llm_def:
        backend_choice = st.radio(
            "LLM backend",
            ["Anthropic API (Claude)", "Ollama (local)"],
            key="run_llm_backend",
            horizontal=True,
        )
        if backend_choice == "Anthropic API (Claude)":
            import os
            llm_backend = "anthropic"
            llm_model = st.selectbox(
                "Claude model",
                ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-7"],
                key="run_claude_model",
                help="Haiku is fastest and cheapest. Sonnet gives better results.",
            )
            api_key_env = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key_env:
                st.warning(
                    "ANTHROPIC_API_KEY environment variable not set. "
                    "Set it before starting the dashboard: "
                    "`$env:ANTHROPIC_API_KEY = 'sk-ant-...'`"
                )
        else:
            llm_backend = "ollama"
            llm_model = st.text_input(
                "Ollama model", value="gemma4:26b", key="run_llm_model",
                help="Any model you have pulled in Ollama. First run loads the model (~30s)."
            )

    if st.button("Run Pipeline", disabled=uploaded is None, type="primary"):
        harvester = _build_harvester(use_llm_ner, llm_backend or "ollama", llm_model or "gemma4:26b")
        _run(
            ctx,
            uploaded,
            source_system=source_system or "upload",
            approved_by=approved_by.strip() or None,
            harvester=harvester,
            llm_backend=llm_backend if use_llm_def else None,
            llm_model=llm_model if use_llm_def else None,
        )


def _build_backend(backend: str, model: str):
    if backend == "anthropic":
        try:
            from ontobridge.agents.ner.backend import AnthropicBackend
            return AnthropicBackend(model=model)
        except ImportError:
            st.error("anthropic package not installed. Run: pip install anthropic")
            st.stop()
        except ValueError as e:
            st.error(str(e))
            st.stop()
    else:
        try:
            from ontobridge.agents.ner.backend import OllamaBackend
            return OllamaBackend(model=model)
        except ImportError:
            st.error("langchain-ollama not installed. Run: pip install langchain-ollama langchain-core")
            st.stop()


def _build_harvester(use_llm: bool, backend: str, model: str) -> HarvesterAgent:
    if use_llm:
        from ontobridge.agents.ner.extractor import LLMNerExtractor
        llm = _build_backend(backend, model)
        return HarvesterAgent(extractor=LLMNerExtractor(llm))
    return HarvesterAgent()


def _run(
    ctx: DashboardContext,
    uploaded,
    *,
    source_system: str,
    approved_by: str | None,
    harvester: HarvesterAgent,
    llm_backend: str | None,
    llm_model: str | None,
) -> None:
    progress_bar = st.progress(0, text="Starting pipeline...")

    definition_agent = None
    if llm_backend and llm_model:
        from ontobridge.agents.definition.agent import LLMDefinitionAgent
        definition_agent = LLMDefinitionAgent(_build_backend(llm_backend, llm_model))

    suffix = Path(uploaded.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.read())
        tmp_path = Path(tmp.name)

    try:
        runner = BatchPipelineRunner(
            ontology=ctx.ontology,
            publisher=ctx.publisher,
            harvester=harvester,
            definition_agent=definition_agent,
            on_progress=lambda done, total: progress_bar.progress(
                done / total,
                text=f"Processing term {done} / {total}...",
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
            "Check that the file contains business term definitions, "
            "or enable the LLM extractor for natural prose."
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
