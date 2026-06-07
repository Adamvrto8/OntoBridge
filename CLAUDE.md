# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow

Follow this sequence for every non-trivial task:

1. **Explore** — read the relevant files before touching anything. Understand what exists.
2. **Plan** — propose the approach and confirm with the user before writing code.
3. **Code** — implement. One logical change per step. Run tests after each change.
4. **Commit** — only when the user explicitly asks. Never push unless asked.

For small tasks (typo fix, single-line change) skip straight to code.
For anything touching the pipeline, agents, or API — always explore and plan first.

## Commands

### Backend

```powershell
# Install (from ontobridge/ directory)
pip install -e ".[api,readers,llm]"
pip install anthropic   # for Claude API support
pip install rdflib      # for FIBO ontology matching

# Run API server (demo mode — resets on restart)
# NOTE: do NOT use --reload; FIBO index takes 1-3 min to load at startup
cd "c:\Users\Tomáš Kočí\OntoBridge\OntoBridge"; uvicorn api_server:app

# Run API server (persistent SQLite)
$env:DB_PATH = "ontobridge.db"; uvicorn api_server:app

# Kill all running backend/frontend processes
taskkill /F /IM uvicorn.exe; taskkill /F /IM python.exe; taskkill /F /IM node.exe

# Shared team server (builds frontend, binds 0.0.0.0, prints LAN IP)
.\start_server.ps1 -Port 8001          # port 8000 taken on this machine
.\start_server.ps1 -Port 8001 -NoBuild # skip npm build
.\start_server.ps1 -Port 8001 -Demo    # in-memory mode

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

**Important:** every Python change requires a manual backend restart (no --reload). Wait for `FIBO index ready.` in the terminal before submitting pipeline requests.

## Architecture

### Interface

- **React + Vite** (`frontend/`) — the UI, runs on port 5173, Vite proxies `/api/*` to FastAPI on port 8000 (8001 on Adam's machine). The Streamlit app has been removed; React is the only frontend.

### Per-bank ontology (deployment model)

The ontology is **not** hardcoded. `create_app(ontology_path=...)` injects it, and `api_server.py` reads the `ONTOLOGY_PATH` env var (default `ontology/ontobridge_ontology_v0.1.ttl`). Every agent reads from the loaded `OntologyIndex`. A deploying bank supplies its own SKOS/OWL TTL; `ontology/sample_bank_acme.ttl` is a worked example. Three layers: FIBO (industry) → baseline (`ontobridge_ontology_v0.1.ttl`) → bank-specific. Startup logs a one-line summary (concepts / schemes / relation pairs).

### Request flow

```
Browser → Vite dev server (:5173)
    /api/* → FastAPI (:8000)
        app.state.publisher     (InMemoryPublisher or SqlitePublisher)
        app.state.ontology      (OntologyIndex from .ttl file)
        app.state.audit_log
        app.state.fibo_matcher  (FiboMatcher, loaded once at startup)
```

State is stored on `app.state` at startup in `src/ontobridge/api/main.py` via FastAPI lifespan. All routers access it through typed dependency functions in `src/ontobridge/api/deps.py` (`PublisherDep`, `AuditDep`, `OntologyDep`, `FiboMatcherDep`).

### Pipeline execution order

Each document upload triggers `BatchPipelineRunner.run_document()` → deduplication by FIBO URI → `PipelineRunner.run()` per term:

```
HarvesterAgent      reads file, calls extractor per RawDocument chunk
  ↓ EnrichedTerm with candidate_labels + definition
FiboMatcher         label/synonym/abbreviation lookup against FIBO index
  ↓ fibo_match (uri, match_type, broader_uri, broader_label, module, alt_labels)
MappingAgent        duplicate/fuzzy detection against published glossary
TaxonomyAgent       FIBO hierarchy placement (falls back to ontology similarity)
LLMDefinitionAgent  (optional) rewrites definition + generates IF/THEN business rules
RelationsAgent      4-stage relation extraction (see below)
PipelineRunner      resolves relation object labels to published term URIs
GovernanceAgent     evaluates 14 rules → GovResult (findings, recommended_action)
WriterAgent         mints term URI, serialises to Turtle, calls publisher.create_term()
```

All tuneable thresholds live in `src/ontobridge/pipeline_config.py` (`PipelineConfig`).

#### `run()` vs `ingest()` — create vs steady-state upsert

`PipelineRunner.run()` always mints a new term (used by seeding and direct callers). `PipelineRunner.ingest()` is the **dedup-aware** entry point used by `BatchPipelineRunner` (and the upload API):

- Exact DUPLICATE, or FUZZY ≥ `config.merge_threshold` (0.92), against an **already-published** term → merge instead of create. The new document is appended as provenance and new synonyms are folded in; the published definition is **never** overwritten.
- If the incoming definition has drifted from the published one (similarity < `config.drift_threshold`, 0.85), the existing term is flipped to REVIEW.
- A match against an unpublished baseline-ontology concept still mints the term (it's the first time we see it).

`ingest()` returns a `RunResult{term, action}` with `action ∈ {created, merged, drifted}`. `BatchResult` has matching `published` / `merged` / `drifted` buckets, surfaced by the pipeline API as counts (e.g. "12 new, 340 merged, 5 drift").

#### RelationsAgent — 4 stages

1. **SVO text extraction** (always) — regex heuristic over definition + policy_context paragraphs → `source="svo"`
2. **FIBO OWL restrictions** (when `fibo_match` exists) — reads `FiboIndex.restrictions_by_uri` for the matched FIBO URI:
   - exact match + inverse_uri → `RESOLVED`, `source="fibo"`, confidence 0.9
   - exact match without inverse_uri → `PROPOSED` fallback, `source="fibo"`, confidence 0.75
   - close/broad match → all restrictions as `PROPOSED`, `source="fibo"`, confidence 0.7
   - always appends a `skos:exactMatch` or `skos:closeMatch` FIBO_MATCH relation to the FIBO URI
3. **Inherited FIBO from broader concept** (when no `fibo_match`) — extracts label from `taxonomy_placement.broader_concept_uri`, looks it up in FIBO, passes its restrictions to LLM as context only (not shown in UI directly — too generic, e.g. FND/Customer has `buysFrom → Supplier`)
4. **LLM proposals** (when `llm_backend` set) — runs for ALL terms regardless of FIBO match; receives FIBO restrictions as context → `PROPOSED`, `source="llm"`, confidence 0.5

#### BatchPipelineRunner — FIBO URI deduplication

Before processing, `_deduplicate_by_fibo()` groups terms sharing the same `fibo_match.uri`. The winner is the term with the best `match_type` (exact > close > broad). Loser's `candidate_labels` are merged into winner as lower-confidence alt_labels. Losers go to `BatchResult.skipped` with reason `"merged into '...' (same FIBO URI: ...)"`.

Example: uploading a document containing both "Loan-to-Value Ratio" (exact match) and "LTV" (close match) → only "Loan-to-Value Ratio" is published, "ltv" becomes its alt_label.

### Key data models

- `EnrichedTerm` (`models/enrichment.py`) — the central object passed through every pipeline stage. Contains `candidate_labels`, `definition`, `fibo_match`, `taxonomy_placement`, `relations`, `governance_result`.
- `PublishedTerm` (`models/published.py`) — wraps `EnrichedTerm` with `term_uri`, `lifecycle_status`, `approved_by`, `version`.
- `FIBOMatch` (`models/fibo.py`) — `uri`, `match_type` ("exact"/"close"/"broad"), `expected_definition`, `alt_labels`, `broader_uri`, `broader_label`, `module`.
- `SemanticRelation` (`models/enrichment.py`) — `subject_uri`, `predicate_uri`, `object_label`, `object_uri`, `verb`, `status`, `source` ("fibo"/"llm"/"svo"), `confidence`.
- `GovResult` (`agents/governance/models.py`) — `findings: list[RuleFinding]`, `recommended_action` (block/draft/review/publish), `blocking_flags`.

#### RelationStatus enum (`models/enums.py`)

| Value | Meaning | UI colour |
|-------|---------|-----------|
| `resolved` | Confirmed relation with both predicate_uri and inverse_predicate_uri | green |
| `confirmed` | Steward-approved proposal without lexicon URI | green |
| `fibo_match` | skos:exactMatch / skos:closeMatch link to FIBO URI | green |
| `proposed` | Awaiting steward approval (from FIBO or LLM) | amber |
| `unresolved_verb` | SVO extraction — verb not in InverseVerbLexicon | grey |

### Relation stewardship

Stewards approve or reject individual `proposed` relations via:

```
PATCH /api/terms/{term_uri}/relations
Body: { "verb": "influences", "object_label": "Mortgage Interest Rate", "action": "approve" | "reject" }
```

- **approve**: status → `RESOLVED` (if predicate_uri + inverse_predicate_uri exist) or `CONFIRMED` (if no URI)
- **reject**: removes the relation from the list

Relations are identified by `(verb, object_label)` pair. Frontend sends `r.verb` (raw string), not `r.predicate` (display label).

### Term URI navigation

Term URIs contain slashes (e.g. `http://ontobridge.dev/ontology/bank/Loan`). React Router decodes `%2F` back to `/` in path params, breaking routing. Solution used throughout: query param `?uri=` with `encodeURIComponent()` on the frontend, and `{term_id:path}` wildcard on the backend router.

### FIBO integration

`FiboIndex` (`agents/fibo/loader.py`) is built once at server startup via lifespan in `api/main.py`, stored on `app.state.fibo_matcher`, and injected into routes via `FiboMatcherDep`. It indexes:

- `rdfs:label`, `skos:altLabel` — primary label matching
- `cmns-av:synonym`, `cmns-av:abbreviation` — synonym/abbreviation matching
- `rdfs:subClassOf` (named) — taxonomy hierarchy (`parent_by_uri`)
- `rdfs:subClassOf` (BNode) — OWL restrictions (`restrictions_by_uri`): pattern `Class subClassOf [owl:Restriction onProperty P someValuesFrom/onClass R]`
- `owl:inverseOf` — both directions (`inverse_of`)

FIBO folder is auto-detected at `ontology/fibo`, `../fibo`, `./fibo`, `./fibo-master`, `./fibo-master/fibo-master`. Server prints `FIBO index ready.` when done (1–3 min first run).

#### FIBO modules (indexed)

| Module | Classes | Domain |
|--------|---------|--------|
| FBC | 9 983 | Financial Business and Commerce — banks, accounts, payments, clients, regulation |
| FND | 1 501 | Foundations — generic concepts (Agent, Party, Customer, Contract, Money) |
| SEC | 1 315 | Securities — stocks, bonds, derivatives |
| BE | 996 | Business Entities — legal persons, corporations |
| IND | 766 | Indicators — interest rates, economic indices |
| DER | 463 | Derivatives — futures, swaps, options |
| BP | 417 | Business Processes |
| LOAN | 341 | Loans — mortgages, repayment, LTV |
| ACTUS | 244 | ACTUS — standardised financial contract models |
| MD | 156 | Market Data |
| CAE | 153 | Corporate Actions and Events |

**Note:** FND concepts (Customer, Client, Party…) are generic. FIBO `Customer` has only `buysFrom → Supplier` which is wrong for banking. Prefer FBC/LOAN matches when available. `Borrower` (FBC) has `owes → debt`.

### Ontology layer — what gets emitted per term

`WriterAgent` (`agents/writer/agent.py`) serialises each `PublishedTerm` to Turtle. Every term is a `skos:Concept`. Namespaces used: `skos`, `owl`, `rdfs`, `dct`, `bank:` (`http://ontobridge.dev/ontology/bank/`), `bank-rel:` (`http://ontobridge.dev/ontology/bank/relations/`).

#### Labels

```turtle
bank:LoanToValueRatio
    a skos:Concept ;
    skos:prefLabel  "Loan-to-Value Ratio"@en ;
    skos:altLabel   "ltv"@en ;          # all other candidate_labels
```

`candidate_labels` from `EnrichedTerm` — the highest-confidence label becomes `prefLabel`, rest become `altLabel`. Abbreviations and synonyms matched from FIBO index are folded in as `altLabel` when the term is deduplicated (e.g. LTV merges into Loan-to-Value Ratio).

#### Definition

```turtle
    skos:definition "The percentage of a property's total value..."@en ;
```

#### Taxonomy — skos:broader + skos:inScheme

```turtle
    skos:broader  bank:PercentageMonetaryAmount ;
    skos:inScheme bank:PercentageMonetaryAmount ;
```

Set from `TaxonomyPlacement.broader_concept_uri` and `scheme_uri`. After the term is published, `WriterAgent._add_narrower_to_parent()` also writes the inverse triple into the **parent** term's Turtle:

```turtle
bank:PercentageMonetaryAmount
    skos:narrower bank:LoanToValueRatio .
```

This keeps the hierarchy navigable in both directions without a separate inference step.

#### FIBO mapping — skos:exactMatch / closeMatch / broadMatch

```turtle
    skos:exactMatch <https://spec.edmcouncil.org/fibo/ontology/LOAN/LoansGeneral/Loans/LoanToValueRatio> ;
```

Predicate is chosen from `FIBOMatch.match_type`:

| match_type | SKOS predicate | When |
|-----------|----------------|------|
| `exact` | `skos:exactMatch` | Normalised label == primary FIBO label |
| `close` | `skos:closeMatch` | Synonym / abbreviation match |
| `broad` | `skos:broadMatch` | Partial / fuzzy match |

#### Semantic relations — owl:ObjectProperty + owl:inverseOf

Only `RESOLVED` relations (status = `resolved`) are serialised. Each relation requires both `predicate_uri` and `inverse_predicate_uri`.

```turtle
    bank-rel:isSecuredBy  bank:ResidentialProperty .

bank-rel:isSecuredBy
    a            owl:ObjectProperty ;
    owl:inverseOf bank-rel:secures .

bank-rel:secures
    a            owl:ObjectProperty .

bank:ResidentialProperty
    bank-rel:secures bank:MortgageLoan .   # inverse triple written automatically
```

`WriterAgent._emit_relations()` tracks a `declared` set so each property pair `(predicate_uri, inverse_predicate_uri)` gets its `owl:ObjectProperty` + `owl:inverseOf` declaration exactly once, even if multiple terms share the same property.

Proposed / confirmed / unresolved relations are stored in the publisher but **not** serialised to Turtle — they exist only for steward review in the UI.

#### Business rules — skos:scopeNote

```turtle
    skos:scopeNote "IF the loan-to-value ratio exceeds 80% THEN..."@en ;
    skos:scopeNote "IF a property appraisal decreases THEN..."@en ;
```

Each `BusinessRule.rule_text` from `EnrichedTerm.business_rules` becomes one `skos:scopeNote`. Rules are generated by `LLMDefinitionAgent` (IF/THEN form) or extracted from structured glossary input.

#### Provenance — dct:source

```turtle
    dct:source <policy:mortgage_policy_v2.pdf> ;
```

One triple per `PolicyContext.document_ref`. If `section` is set, the URI includes `#section-{section}`.

#### Editorial note

```turtle
    skos:editorialNote "Generated by OntoBridge pipeline"@en .
```

Always present — marks machine-generated terms for human review.

#### URI derivation

Term URI = `{bank_namespace}{CamelCaseLabel}`, e.g. `http://ontobridge.dev/ontology/bank/LoanToValueRatio`. If `TaxonomyPlacement.domain_prefix` contains a CURIE like `bank:LoanToValueRatio`, the suffix is used directly.

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

### Steward editing API

`PATCH /api/terms/{uri}/edit` accepts a `TermPatch` body (all fields optional):

| Field | Type | Effect |
|---|---|---|
| `definition` | `str` | Replaces the term definition |
| `alt_labels` | `list[str]` | Replaces steward-added alt labels (auto-extracted labels preserved) |
| `broader_concept_uri` | `str` | Overrides taxonomy placement parent |
| `scheme_uri` | `str` | Overrides scheme (auto-derived from concept if omitted) |
| `relations_delete` | `list[int]` | Removes relations by index |
| `relations_add` | `list[{verb, object_label}]` | Adds new relations (verb looked up in InverseVerbLexicon) |
| `actor` | `str` | Steward name recorded in audit log |

Supporting read endpoints:
- `GET /api/stats/concepts` — all ontology concepts with scheme label (for taxonomy dropdown)
- `GET /api/stats/verbs` — known verb labels from OWL ObjectProperties (for relation add autocomplete)

### Ontology

`ontology/ontobridge_ontology_v0.1.ttl` — 110 concepts across 10 schemes (v0.2), 20 relation pairs.

**Semantic placement/dedup:** when `sentence-transformers` is installed (and `ONTOBRIDGE_EMBEDDINGS` is not `0`), the API path uses a `SentenceTransformerEncoder` for MappingAgent + TaxonomyAgent instead of the TF-IDF fallback — markedly better taxonomy placement and dedup. Built once via `build_encoder()` in `api/routers/pipeline.py`, warmed at startup. Tests/seed still use TF-IDF (deterministic).
Schemes: Party, Product, Process, Risk, Document, Channel, Compliance, Pricing, Organisation, IT/Data.
Loaded at startup into `OntologyIndex`; injected via `OntologyDep` in all routers that need it.
A concept cannot be its own broader concept (`_rank_parents` skips exact-label matches).

### CSS design system

The frontend uses a custom CSS design system in `frontend/src/index.css` (no Tailwind utility classes in JSX). Key variables: `--ink`, `--ice`, `--slate-d`, `--red`, `--amber`, `--green`, `--surface`. Layout is CSS grid: `grid-template-areas: "side top" "side main"`. Use existing classes (`.card`, `.card-h`, `.card-b`, `.pill`, `.btn`, `.badge`, `.scheme-pill`, `.lifecycle`, `.issues`) rather than inline styles where possible.

### Frontend API client

`frontend/src/api/client.js` — all requests have a 30 s default timeout; pipeline calls (`POST /pipeline/run`) use 600 000 ms (10 min) because LLM extraction on long documents can take many minutes. Timeout fires `AbortError` → shown as "Request timed out" in UI.

### FIBO directory — path may vary

The FIBO ontology files are **not** included in this repository. They must be cloned separately from [github.com/edmcouncil/fibo](https://github.com/edmcouncil/fibo). The auto-detection logic in `api/routers/pipeline.py` (`_find_fibo_dir()`) tries the following candidates in order:

```
{repo_root}/ontology/fibo        ← current default (symlink or clone here)
{repo_root}/fibo-master/fibo-master
{repo_root}/fibo-master
{repo_root}/fibo
{repo_root}/../fibo              ← clone next to the repo
```

If none of these exist the server starts without FIBO matching and prints `FIBO directory not found — running without FIBO matching.`

**To add a new path:** edit the `candidates` list in `_find_fibo_dir()` in `src/ontobridge/api/routers/pipeline.py`. The directory must contain `.ttl` / `.rdf` / `.owl` files recursively — the loader walks the entire subtree.
