from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ontobridge.api.routers import audit, graph, pipeline, stats, terms


def create_app(
    ontology_path: str | Path = "ontology/ontobridge_ontology_v0.1.ttl",
    db_path: str | Path | None = None,
) -> FastAPI:
    ontology_path = Path(ontology_path)
    db_path = Path(db_path) if db_path else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from ontobridge.dashboard.seed import build_sample_publisher, load_ontology
        from ontobridge.audit import InMemoryAuditLog

        ontology = load_ontology(str(ontology_path))
        app.state.ontology = ontology

        if db_path is not None:
            from ontobridge.publisher import SqlitePublisher
            from ontobridge.audit import SqliteAuditLog
            publisher = SqlitePublisher(str(db_path))
            if publisher.count() == 0:
                seeded = build_sample_publisher(ontology)
                for term in seeded.search_terms(""):
                    publisher.create_term(term)
            audit_path = db_path.with_stem(db_path.stem + "_audit")
            audit_log = SqliteAuditLog(str(audit_path))
        else:
            publisher = build_sample_publisher(ontology)
            audit_log = InMemoryAuditLog()

        app.state.publisher = publisher
        app.state.audit_log = audit_log

        # FIBO index — loaded once at startup so pipeline requests never block
        try:
            from ontobridge.api.routers.pipeline import _build_fibo_matcher
            print("Loading FIBO index (this may take 1–3 minutes on first run)…")
            app.state.fibo_matcher = _build_fibo_matcher()
            if app.state.fibo_matcher:
                print("FIBO index ready.")
            else:
                print("FIBO directory not found — running without FIBO matching.")
        except Exception as exc:
            print(f"FIBO loading failed: {exc} — running without FIBO matching.")
            app.state.fibo_matcher = None

        yield

    app = FastAPI(
        title="OntoBridge API",
        description="Semantic term governance REST API",
        version="0.1.0",
        lifespan=lifespan,
    )

    _cors_env = os.environ.get("CORS_ORIGINS", "")
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(terms.router, prefix="/api")
    app.include_router(pipeline.router, prefix="/api")
    app.include_router(audit.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")
    app.include_router(graph.router, prefix="/api")

    # Serve built React frontend if it exists
    frontend_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app
