# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend

```powershell
# Install (from ontobridge/ directory)
pip install -e ".[api,readers,llm]"
pip install anthropic   # for Claude API support
pip install rdflib      # for FIBO ontology matching

# Run API server (demo mode — resets on restart)
uvicorn api_server:app --reload

# Run API server (persistent SQLite)
$env:DB_PATH = "ontobridge.db"; uvicorn api_server:app --reload

# Shared team server (builds frontend, binds 0.0.0.0, prints LAN IP)
.\start_server.ps1
.\start_server.ps1 -NoBuild    # skip npm build
.\start_server.ps1 -Demo       # in-memory mode
.\start_server.ps1 -Port 8080  # custom port

# Run all tests
pytest

# Run a single test file
pytest tests/test_relations_agent.py -v

# Run a single test by name
pytest tests/test_relations_agent.py::test_holds_relation_resolves_to_bank_rel_holds_held_by -v

# Run tests matching a keyword
pytest -k "fibo" -v
```

### Frontend

```bash
# From ontobridge/frontend/
npm install
npm run dev      # dev server at http://localhost:5173
npm run build
npm run lint
```

## Architecture

### Two interfaces, one backend

- **React + Vite** (`frontend/`) — production UI, runs on port 5173, Vite proxies `/api/*` to FastAPI on port 8000
- **Streamlit** (`streamlit_app.py`) — testing/internal tooling, port 8501, reads the same publisher state

### Request flow

```
Browser → Vite dev server (:5173)
    /api/* → FastAPI (:8000)
        app.state.publisher  (InMemoryPublisher or SqlitePublisher)
        app.state.ontology   (OntologyIndex from .ttl file)
        app.state.audit_log
```

State is stored on `app.state` at startup in `src/ontobridge/api/main.py` via FastAPI lifespan. All routers access it through typed dependency functions in `src/ontobridge/api/deps.py` (`PublisherDep`, `AuditDep`, `OntologyDep`).

### Pipeline execution order

Each document upload triggers `BatchPipelineRunner.run_document()` → `PipelineRunner.run()` per term:

```
HarvesterAgent      reads file, calls extractor per RawDocument chunk
  ↓ EnrichedTerm with candidate_labels + definition
FiboMatcher         label/synonym/abbreviation lookup against FIBO index
  ↓ fibo_match (uri, broader_uri, broader_label, module, alt_labels)
MappingAgent        duplicate/fuzzy detection against published glossary
TaxonomyAgent       FIBO hierarchy placement (falls back to ontology similarity)
LLMDefinitionAgent  (optional) rewrites definition + generates IF/THEN business rules
RelationsAgent      SVO regex extraction + FIBO skos:closeMatch injection
PipelineRunner      resolves relation object labels to published term URIs
GovernanceAgent     evaluates 14 rules → GovResult (findings, recommended_action)
WriterAgent         mints term URI, serialises to Turtle, calls publisher.create_term()
```

All tuneable thresholds live in `src/ontobridge/pipeline_config.py` (`PipelineConfig`).

### Key data models

- `EnrichedTerm` (`models/enrichment.py`) — the central object passed through every pipeline stage. Contains `candidate_labels`, `definition`, `fibo_match`, `taxonomy_placement`, `relations`, `governance_result`.
- `PublishedTerm` (`models/published.py`) — wraps `EnrichedTerm` with `term_uri`, `lifecycle_status`, `approved_by`, `version`.
- `FIBOMatch` (`models/fibo.py`) — `uri`, `expected_definition`, `alt_labels`, `broader_uri`, `broader_label`, `module`.
- `SemanticRelation` (`models/enrichment.py`) — `subject_uri`, `predicate_uri`, `object_label`, `object_uri`, `verb`, `status` (RESOLVED / UNRESOLVED_VERB / FIBO_MATCH).
- `GovResult` (`agents/governance/models.py`) — `findings: list[RuleFinding]`, `recommended_action` (block/draft/review/publish), `blocking_flags`.

### Term URI navigation

Term URIs contain slashes (e.g. `http://ontobridge.dev/ontology/bank/Loan`). React Router decodes `%2F` back to `/` in path params, breaking routing. Solution used throughout: query param `?uri=` with `encodeURIComponent()` on the frontend, and `{term_id:path}` wildcard on the backend router.

### FIBO integration

`FiboIndex` (`agents/fibo/loader.py`) is built once and cached as a module-level singleton in `api/routers/pipeline.py`. It indexes:
- `rdfs:label`, `skos:altLabel` — for primary label matching
- `cmns-av:synonym`, `cmns-av:abbreviation` — for synonym/abbreviation matching (418 + 810 entries)
- `rdfs:subClassOf` — for taxonomy hierarchy (2884 parent relationships)

FIBO folder is auto-detected at `../fibo`, `./fibo`, `./fibo-master`, `./fibo-master/fibo-master`. First pipeline run after server restart is slow (~30–60s) while FIBO loads; subsequent runs use the cache.

### Governance rules

14 rules in `agents/governance/rules/`. Rules are evaluated in `GovernanceAgent.evaluate(candidate)` where `Candidate` is built from `EnrichedTerm` in `PipelineRunner._term_to_candidate()`. `recommended_action` maps to `LifecycleStatus`: block→CANDIDATE, draft→DRAFT, review→REVIEW, publish→PUBLISHED.

`_ACTION_TO_SEVERITY` in `api/schemas.py` maps `recommended_action` to inbox severity: block→crit, draft→high, review→med, publish→low.

### Publisher abstraction

`TermPublisher` (`publisher/base.py`) is an ABC with two implementations:
- `InMemoryPublisher` — default, resets on restart
- `SqlitePublisher` — persistent, enabled via `DB_PATH` env var

Both accept `approved_by` in `transition_status()`. Transitioning to PUBLISHED requires `approved_by` to be set (either passed in or already on the term).

### Adding a new governance rule

1. Create a class in the appropriate `agents/governance/rules/*.py` file extending `Rule` with `rule_id`, `category`, `title`, and `evaluate(candidate, ontology) -> RuleFinding`.
2. Import and add it to `default_rules()` in `agents/governance/rules/__init__.py`.
3. Rule IDs must be unique integers (currently 1–14).

### Adding a new API route

1. Create or edit a router file in `src/ontobridge/api/routers/`.
2. Import and register it in `src/ontobridge/api/main.py` with `app.include_router(..., prefix="/api")`.
3. Add the corresponding client call in `frontend/src/api/client.js`.

### CSS design system

The frontend uses a custom CSS design system in `frontend/src/index.css` (no Tailwind utility classes in JSX). Key variables: `--ink`, `--ice`, `--slate-d`, `--red`, `--amber`, `--green`, `--surface`. Layout is CSS grid: `grid-template-areas: "side top" "side main"`. Use existing classes (`.card`, `.card-h`, `.card-b`, `.pill`, `.btn`, `.badge`, `.scheme-pill`, `.lifecycle`, `.issues`) rather than inline styles where possible.
