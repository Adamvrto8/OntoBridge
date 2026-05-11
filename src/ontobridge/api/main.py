from __future__ import annotations

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
        yield

    app = FastAPI(
        title="OntoBridge API",
        description="Semantic term governance REST API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
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
    frontend_dist = Path(__file__).resolve().parents[4] / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app
