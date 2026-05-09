from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile

from ontobridge.api.deps import AuditDep, OntologyDep, PublisherDep
from ontobridge.api.schemas import PipelineRunResponse, TermSummary
from ontobridge.agents.fibo import FiboIndex, FiboMatcher
from ontobridge.agents.harvester.agent import HarvesterAgent
from ontobridge.batch import BatchPipelineRunner

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _build_backend(backend: str, model: str):
    if backend == "anthropic":
        from ontobridge.agents.ner.backend import AnthropicBackend
        return AnthropicBackend(model=model)
    from ontobridge.agents.ner.backend import OllamaBackend
    return OllamaBackend(model=model)


def _find_fibo_paths() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[4]
    fibo_dir = repo_root / "fibo-master" / "fibo-master"
    if not fibo_dir.exists() or not fibo_dir.is_dir():
        return []
    return [
        path
        for path in fibo_dir.rglob("*")
        if path.suffix.lower() in {".ttl", ".rdf", ".owl", ".xml", ".nt", ".jsonld"}
    ]


def _build_fibo_matcher() -> FiboMatcher | None:
    paths = _find_fibo_paths()
    if not paths:
        return None

    index = FiboIndex.from_paths(paths)
    return FiboMatcher(index)


@router.post("/run", response_model=PipelineRunResponse)
async def run_pipeline(
    publisher: PublisherDep,
    ontology: OntologyDep,
    audit: AuditDep,
    file: UploadFile,
    source_system: str = Form(default="upload"),
    approved_by: str = Form(default=""),
    use_llm_ner: bool = Form(default=False),
    use_llm_def: bool = Form(default=False),
    llm_backend: str = Form(default="ollama"),
    llm_model: str = Form(default="gemma4:26b"),
):
    fibo_matcher = _build_fibo_matcher()
    harvester = HarvesterAgent(fibo_matcher=fibo_matcher)
    if use_llm_ner:
        try:
            from ontobridge.agents.ner.extractor import LLMNerExtractor
            harvester = HarvesterAgent(
                extractor=LLMNerExtractor(_build_backend(llm_backend, llm_model)),
                fibo_matcher=fibo_matcher,
            )
        except (ImportError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e))

    definition_agent = None
    if use_llm_def:
        try:
            from ontobridge.agents.definition.agent import LLMDefinitionAgent
            definition_agent = LLMDefinitionAgent(_build_backend(llm_backend, llm_model))
        except (ImportError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e))

    suffix = Path(file.filename or "upload.txt").suffix
    content = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        runner = BatchPipelineRunner(
            ontology=ontology,
            publisher=publisher,
            harvester=harvester,
            definition_agent=definition_agent,
        )
        result = runner.run_document(
            tmp_path,
            source_system=source_system or "upload",
            document_id=file.filename,
            approved_by=approved_by.strip() or None,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    return PipelineRunResponse(
        published=len(result.published),
        skipped=len(result.skipped),
        failed=len(result.failed),
        terms=[TermSummary.from_published(t) for t in result.published],
    )
