from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile

from ontobridge.api.deps import AuditDep, FiboMatcherDep, OntologyDep, PublisherDep
from ontobridge.api.schemas import PipelineRunResponse, TermSummary
from ontobridge.agents.fibo import FiboIndex, FiboMatcher
from ontobridge.agents.harvester.agent import HarvesterAgent
from ontobridge.batch import BatchPipelineRunner

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _build_backend(backend: str, model: str, api_key: str | None = None):
    if backend == "anthropic":
        from ontobridge.agents.ner.backend import AnthropicBackend
        return AnthropicBackend(model=model, api_key=api_key or None)
    from ontobridge.agents.ner.backend import OllamaBackend
    return OllamaBackend(model=model)


_FIBO_NOT_LOADED = object()
_fibo_matcher_cache: object = _FIBO_NOT_LOADED


def _find_fibo_dir() -> Path | None:
    repo_root = Path(__file__).resolve().parents[4]
    candidates = [
        repo_root / "ontology" / "fibo",
        repo_root / "fibo-master" / "fibo-master",
        repo_root / "fibo-master",
        repo_root / "fibo",
        repo_root.parent / "fibo",
    ]
    return next((p for p in candidates if p.exists() and p.is_dir()), None)


def _build_fibo_matcher() -> FiboMatcher | None:
    global _fibo_matcher_cache
    if _fibo_matcher_cache is not _FIBO_NOT_LOADED:
        return _fibo_matcher_cache  # type: ignore[return-value]

    fibo_dir = _find_fibo_dir()
    if fibo_dir is None:
        _fibo_matcher_cache = None
        return None

    paths = [
        p for p in fibo_dir.rglob("*")
        if p.suffix.lower() in {".ttl", ".rdf", ".owl", ".xml", ".nt", ".jsonld"}
    ]
    index = FiboIndex.from_paths(paths)
    _fibo_matcher_cache = FiboMatcher(index)
    return _fibo_matcher_cache  # type: ignore[return-value]


@router.post("/run", response_model=PipelineRunResponse)
async def run_pipeline(
    publisher: PublisherDep,
    ontology: OntologyDep,
    audit: AuditDep,
    fibo_matcher: FiboMatcherDep,
    file: UploadFile,
    source_system: str = Form(default="upload"),
    approved_by: str = Form(default=""),
    use_llm_ner: bool = Form(default=False),
    use_llm_def: bool = Form(default=False),
    llm_backend: str = Form(default="ollama"),
    llm_model: str = Form(default="gemma4:26b"),
    llm_api_key: str = Form(default=""),
):
    api_key = llm_api_key.strip() or None
    harvester = HarvesterAgent(fibo_matcher=fibo_matcher)
    if use_llm_ner:
        try:
            from ontobridge.agents.ner.extractor import LLMNerExtractor
            harvester = HarvesterAgent(
                extractor=LLMNerExtractor(_build_backend(llm_backend, llm_model, api_key)),
                fibo_matcher=fibo_matcher,
            )
        except (ImportError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e))

    definition_agent = None
    if use_llm_def:
        try:
            from ontobridge.agents.definition.agent import LLMDefinitionAgent
            definition_agent = LLMDefinitionAgent(_build_backend(llm_backend, llm_model, api_key))
        except (ImportError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e))

    suffix = Path(file.filename or "upload.txt").suffix
    content = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        from ontobridge.agents.policy_linker import TFIDFPolicyLinker
        policy_linker = TFIDFPolicyLinker(threshold=0.30, top_k=3)
        try:
            policy_linker.index_document(tmp_path, document_ref=file.filename)
        except Exception:
            policy_linker = None  # indexing failed — proceed without linker

        runner = BatchPipelineRunner(
            ontology=ontology,
            publisher=publisher,
            harvester=harvester,
            definition_agent=definition_agent,
            fibo_matcher=fibo_matcher,
            policy_linker=policy_linker,
        )
        result = runner.run_document(
            tmp_path,
            source_system=source_system or "upload",
            document_id=file.filename,
            approved_by=approved_by.strip() or None,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"{type(e).__name__}: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    return PipelineRunResponse(
        published=len(result.published),
        skipped=len(result.skipped),
        failed=len(result.failed),
        terms=[TermSummary.from_published(t) for t in result.published],
    )
