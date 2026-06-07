from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from ontobridge.api.deps import AuditDep, FiboMatcherDep, OntologyDep, PublisherDep
from ontobridge.api.schemas import PipelineRunResponse, SkippedTermOut, TermSummary
from ontobridge.agents.fibo import FiboIndex, FiboMatcher
from ontobridge.agents.harvester.agent import HarvesterAgent
from ontobridge.batch import BatchPipelineRunner, BatchResult
from ontobridge.integrations.dawiso import get_publisher
from ontobridge.pipeline_config import PipelineConfig

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


_ENCODER_NOT_LOADED = object()
_encoder_cache: object = _ENCODER_NOT_LOADED


def build_encoder():
    """Shared dense encoder for mapping + taxonomy, cached across requests so the
    model loads once and concept embeddings stay warm.

    Sentence-transformer embeddings give far better taxonomy placement and
    dedup than the TF-IDF fallback. Returns ``None`` (TF-IDF fallback) when
    sentence-transformers is not installed or is disabled via
    ``ONTOBRIDGE_EMBEDDINGS=0``.
    """
    global _encoder_cache
    if _encoder_cache is not _ENCODER_NOT_LOADED:
        return _encoder_cache
    if os.environ.get("ONTOBRIDGE_EMBEDDINGS", "1").lower() in {"0", "false", "no"}:
        _encoder_cache = None
        return None
    try:
        from ontobridge.encoders.sentence_transformer import SentenceTransformerEncoder
        enc = SentenceTransformerEncoder()
        enc.encode("warm up")  # load the model now so import errors surface early
        _encoder_cache = enc
    except Exception:
        _encoder_cache = None
    return _encoder_cache


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
    files: list[UploadFile] = File(...),
    source_system: str = Form(default="upload"),
    approved_by: str = Form(default=""),
    use_llm_ner: bool = Form(default=False),
    use_llm_def: bool = Form(default=False),
    use_llm_rel: bool = Form(default=False),
    llm_backend: str = Form(default="ollama"),
    llm_model: str = Form(default="gemma4:26b"),
    llm_api_key: str = Form(default=""),
):
    if not files:
        raise HTTPException(status_code=422, detail="No files uploaded.")

    api_key = llm_api_key.strip() or None

    # Build a single LLM backend if any LLM feature needs one, and reuse it for
    # extraction, definitions, relations, and synonym dedup. This decouples LLM
    # relation extraction from the "improve definitions" toggle.
    backend = None
    if use_llm_ner or use_llm_def or use_llm_rel:
        try:
            backend = _build_backend(llm_backend, llm_model, api_key)
        except (ImportError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e))

    harvester = HarvesterAgent(fibo_matcher=fibo_matcher)
    if use_llm_ner:
        try:
            from ontobridge.agents.ner.extractor import LLMNerExtractor
            harvester = HarvesterAgent(
                extractor=LLMNerExtractor(backend),
                fibo_matcher=fibo_matcher,
            )
        except (ImportError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e))

    definition_agent = None
    if use_llm_def:
        try:
            from ontobridge.agents.definition.agent import LLMDefinitionAgent
            definition_agent = LLMDefinitionAgent(backend)
        except (ImportError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e))

    # Relations reuse whatever backend the run already built — so enabling LLM
    # NER (or definitions, or use_llm_rel) is enough to get LLM relations. A
    # pure pattern-only run builds no backend, so relations stay on SVO.
    rel_backend = backend

    # Persist every uploaded document to a temp file (multi-file upload).
    tmp_paths: list[tuple[Path, str]] = []
    for upload in files:
        suffix = Path(upload.filename or "upload.txt").suffix
        content = await upload.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_paths.append((Path(tmp.name), upload.filename or "upload.txt"))

    try:
        from ontobridge.agents.policy_linker import TFIDFPolicyLinker
        policy_linker = TFIDFPolicyLinker(threshold=0.30, top_k=3)
        any_indexed = False
        for tmp_path, filename in tmp_paths:
            try:
                policy_linker.index_document(tmp_path, document_ref=filename)
                any_indexed = True
            except Exception:
                pass
        if not any_indexed:
            policy_linker = None  # indexing failed — proceed without linker

        encoder = build_encoder()
        config = PipelineConfig(encoder=encoder) if encoder is not None else None
        dawiso_publisher = get_publisher()  # None unless DAWISO_* env vars set

        # Parallelise per-term LLM enrichment when an LLM is in play (calls are
        # network-bound). Pure pattern runs stay sequential — threads wouldn't
        # help CPU-bound work. Tunable via ONTOBRIDGE_PIPELINE_WORKERS.
        if backend is not None:
            try:
                workers = int(os.environ.get("ONTOBRIDGE_PIPELINE_WORKERS", "8"))
            except ValueError:
                workers = 8
        else:
            workers = 1

        runner = BatchPipelineRunner(
            ontology=ontology,
            publisher=publisher,
            config=config,
            harvester=harvester,
            definition_agent=definition_agent,
            fibo_matcher=fibo_matcher,
            policy_linker=policy_linker,
            llm_backend=rel_backend,
            max_workers=workers,
            dawiso_publisher=dawiso_publisher,
            # Synonym dedup rides with "improve definitions" (matches the UI).
            synonym_dedup=use_llm_def,
        )

        def _run_all() -> BatchResult:
            # Process every document, aggregating all buckets. Run in a worker
            # thread (below) so the LLM-heavy work never blocks uvicorn's event
            # loop — a blocked loop on Windows drops connections (WinError 64)
            # and surfaces as a 502 even though the run succeeds.
            agg = BatchResult()
            try:
                for path, filename in tmp_paths:
                    partial = runner.run_document(
                        path,
                        source_system=source_system or "upload",
                        document_id=filename,
                        approved_by=approved_by.strip() or None,
                    )
                    agg.published.extend(partial.published)
                    agg.merged.extend(partial.merged)
                    agg.drifted.extend(partial.drifted)
                    agg.skipped.extend(partial.skipped)
                    agg.failed.extend(partial.failed)
            finally:
                runner.close()
            return agg

        result = await run_in_threadpool(_run_all)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"{type(e).__name__}: {e}")
    finally:
        for tmp_path, _ in tmp_paths:
            tmp_path.unlink(missing_ok=True)

    return PipelineRunResponse(
        published=len(result.published),
        merged=len(result.merged),
        drifted=len(result.drifted),
        skipped=len(result.skipped),
        failed=len(result.failed),
        terms=[
            TermSummary.from_published(t)
            for t in (result.published + result.drifted)
        ],
        skipped_details=[
            SkippedTermOut(label=(t.preferred_label or "(unlabelled)"), reason=reason)
            for t, reason in result.skipped
        ],
    )
