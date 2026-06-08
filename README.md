# OntoBridge

Multi-agent semantic term governance system for retail banking.  
Extracts business terms from documents, maps them onto a SKOS/OWL ontology, enriches them with FIBO (Financial Industry Business Ontology), and routes them through a human-in-the-loop governance workflow.

The primary interface is the **React web app** — FastAPI backend + Vite/React frontend. A REST API is exposed for integration with external data platforms (Dawiso, Collibra, etc.).

---

## System overview

Retail banks accumulate business terms across policy documents, regulations, and product sheets — usually with inconsistent or missing definitions and no shared vocabulary. OntoBridge turns those documents into a **governed business glossary** instead of curating every term by hand.

Each uploaded document flows through a **multi-agent pipeline**: candidate terms are extracted, anchored to FIBO and the bank's own SKOS/OWL ontology, placed in a taxonomy, given a clean definition and semantic relations, then evaluated by a rule-based **governance** layer that assigns a lifecycle state and routes the term to a human steward.

```
Document → extract → FIBO + ontology match → taxonomy → definition + relations
         → governance (14 rules) → steward review → published glossary term
```

The output is a SKOS/OWL glossary, exportable as Turtle/CSV or pushed to an external data catalog (Dawiso today; Collibra and others via the same opt-in connector). The layers and pipeline stages are detailed in the sections below.

### Three-layer ontology model

OntoBridge governs terms across three layers, from universal to company-specific:

1. **FIBO** — the EDM Council's industry-standard financial ontology (~16k classes). Universal semantic anchor; bundled, never edited.
2. **OntoBridge baseline** — `ontology/ontobridge_ontology_v0.1.ttl`, a retail-banking *reference skeleton* (110 concepts, 10 schemes, 20 relation pairs). The default starting point.
3. **Bank-specific ontology** — a deploying bank supplies its **own** SKOS/OWL schema (its schemes, its product names, its relations) via the `ONTOLOGY_PATH` environment variable. See [Bring your own ontology](#bring-your-own-ontology). `ontology/sample_bank_acme.ttl` is a worked example.

### Deployment

Designed to run **on-premise**, inside the bank's perimeter — sensitive policy documents never leave the building. SQLite is the default store for a single-node pilot; the `TermPublisher` abstraction allows a shared database backend if multiple stewards need concurrent access. No cloud dependency.

---

## Setup & run

Requires **Python 3.10+** (3.12+ recommended) and **Node.js 18+**.

```bash
# 1. Clone
git clone https://github.com/Adamvrto8/OntoBridge.git
cd OntoBridge/ontobridge

# 2. Python virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate         # macOS / Linux

# 3. Install (all extras — API, document readers, LLM, embeddings, NLP, tests)
pip install -e ".[api,readers,llm,claude,dev,embeddings,nlp,mcp]"
python -m spacy download en_core_web_sm

# 4. Frontend
cd frontend && npm install && cd ..
```

Start the backend (in-memory demo mode):

```powershell
python -m uvicorn api_server:app --port 8001
```

Open **http://localhost:8001** (interactive API docs at `/docs`). During frontend work, run `npm run dev` in `frontend/` for hot-reload instead of opening the built app.

Useful environment variables:

| Variable | Effect |
|---|---|
| `DB_PATH=ontobridge.db` | Persist to SQLite instead of in-memory (survives restarts) |
| `ONTOLOGY_PATH=ontology/sample_bank_acme.ttl` | Load a different ontology (see [Bring your own ontology](#bring-your-own-ontology)) |
| `ANTHROPIC_API_KEY=sk-ant-...` | Enable Claude-based LLM extraction (see [LLM extraction](#llm-extraction)) |
| `ONTOBRIDGE_EMBEDDINGS=0` | Force the lighter TF-IDF path instead of sentence-transformers |

> **FIBO** enrichment loads automatically when FIBO is present (see [FIBO ontology integration](#fibo-ontology-integration)). Indexing takes 1–3 minutes at startup, so **do not use `--reload`** — it would re-index on every change.

Run `pytest` to execute the test suite (details under [Running tests](#running-tests)).

---

## Bring your own ontology

OntoBridge ships with a retail-banking **baseline** ontology, but it is not tied to it. A deploying bank points the server at its own SKOS/OWL schema:

```powershell
$env:ONTOLOGY_PATH = "path/to/your_bank.ttl"
python -m uvicorn api_server:app --port 8001
```

Every agent (mapping, taxonomy, governance, relations, writer) reads from whatever ontology is loaded — there is nothing hardcoded to the baseline. `ontology/sample_bank_acme.ttl` is a complete worked example (a fictional digital challenger bank with its own namespace, schemes, and relation lexicon).

### Ontology contract

For the pipeline to make full use of a supplied ontology, the `.ttl` should contain:

| Element | Requirement | Used by |
|---|---|---|
| `skos:ConceptScheme` + `skos:prefLabel` | Top-level domain groupings (your "schemes") | Taxonomy placement, scheme assignment |
| `skos:Concept` + `skos:prefLabel` | One per business concept | Mapping (dedup), taxonomy, governance |
| `skos:definition` | Recommended on every concept | Definition fallback, embedding match quality |
| `skos:altLabel` | Optional synonyms/abbreviations | Dedup recall, acronym matching |
| `skos:broader` | Parent link for hierarchy depth | Taxonomy placement, `skos:narrower` back-links |
| `owl:ObjectProperty` pairs linked by `owl:inverseOf`, **each with `rdfs:label`** (forward **and** inverse) | The relation verb lexicon | Relations agent (SVO + LLM verb resolution) |

Only `skos:Concept` + `skos:prefLabel` is strictly required; everything else degrades gracefully. The startup log reports how many concepts, schemes, and relation pairs were indexed so you can confirm the load.

---

## FIBO ontology integration

OntoBridge optionally integrates with [FIBO](https://spec.edmcouncil.org/fibo/) (Financial Industry Business Ontology).

> **FIBO is not included in this repository** — it is listed in `.gitignore` and must be cloned separately. The server starts and works fully without it; FIBO only adds richer taxonomy placement, alt labels, and definition quality checks.

### Setup

```bash
# Clone next to the ontobridge folder (recommended path)
git clone https://github.com/edmcouncil/fibo.git ../fibo
```

OntoBridge auto-detects FIBO at these paths (checked in order):

```
ontology/fibo/           ← symlink or clone here
../fibo/                 ← sibling of the ontobridge folder (recommended)
./fibo/
./fibo-master/
./fibo-master/fibo-master/
```

No configuration needed. The index loads at server startup (~1–3 minutes, 299 `.ttl` files) and prints `FIBO index ready.` when done.

### What FIBO adds

| Feature | Description |
|---|---|
| **skos:closeMatch** | Semantic link to the official FIBO URI on each matched term |
| **Alt labels** | FIBO synonyms and abbreviations (e.g. "AML", "BIC") injected as alt labels |
| **Taxonomy placement** | FIBO's `rdfs:subClassOf` hierarchy (2884 parent relationships) used for placement |
| **Definition quality check** | Governance Rule 12 compares extracted definition against FIBO's authoritative definition |

---

## LLM extraction

The Run Pipeline page exposes two LLM toggles: **Use LLM extractor** (better NER) and **Improve definitions** (LLM rewrites + IF/THEN business rules).

### Option A — Anthropic Claude

```bash
pip install -e ".[claude]"
```

Set your API key:

**Windows (PowerShell):**
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-api03-..."
# To save permanently:
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
```

**macOS / Linux:**
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

In Run Pipeline: enable an LLM toggle → select **Anthropic API** → choose model → leave key blank to use the env var.

Available models (fastest → best quality):
- `claude-haiku-4-5-20251001`
- `claude-sonnet-4-6`
- `claude-opus-4-8`

### Option B — Ollama (local, no API key needed)

1. Install [Ollama](https://ollama.com/)
2. Pull a model:
   ```bash
   ollama pull llama3.2:1b    # small, fast
   ollama pull gemma4:26b     # larger, better results
   ```
3. In Run Pipeline: enable an LLM toggle → select **Ollama (local)** → enter model name

---

## Running tests

```bash
# Run the full suite (779 tests; optional NLP/embedding tests skip
# automatically when those packages are not installed)
pytest

# Single file
pytest tests/test_relations_agent.py -v

# Filter by name
pytest -k "fibo" -v
```

### Test count explained

| Condition | Result |
|---|---|
| Full dev install (`.[dev,embeddings,nlp]` + spaCy model) | **779 passed** |
| Base install (`.[api,readers,llm]`) | 779 collected; the ~65 tests needing spaCy / sentence-transformers / chromadb skip automatically |

The optional-package tests (`test_spacy_extractors.py`, `test_sentence_transformer_encoder.py`, `test_policy_linker_store.py`) use `pytest.importorskip`, so `pytest` reports a 100% pass rate whether or not those packages are installed.

---

## Platform integration (Dawiso, Collibra, etc.)

OntoBridge exposes a REST API designed for ingestion into external data catalogs.

Publishing a term is **local-only**. Pushing it to an external glossary (Dawiso today, Collibra and others later) is an explicit, opt-in step a steward triggers per term from the **Glossary** or term-detail page (`POST /api/terms/{uri}/publish-dawiso`) — there is no automatic push on approval, so the same term can be sent to multiple catalogs without creating duplicates.

### Authentication

Set `ONTOBRIDGE_API_KEY` on the server to require an API key on all `/api/*` routes. When the env var is not set, auth is disabled (local dev).

```powershell
$env:ONTOBRIDGE_API_KEY = "your-secret-key"   # server side
# External system sends: X-API-Key: your-secret-key
```

### SKOS / TTL export

Pull the full published glossary as a single SKOS/OWL Turtle file:

```
GET /api/terms/export/turtle                  # published terms only (default)
GET /api/terms/export/turtle?status=all       # all terms regardless of status
GET /api/terms/export/turtle?status=published,review
```

The file is a valid RDF graph with `skos:Concept`, `skos:prefLabel`, `skos:definition`, `skos:broader`, and `skos:exactMatch` (FIBO URI) triples — importable directly into any SKOS-aware catalog.

### Webhook (push on term approval)

When `ONTOBRIDGE_WEBHOOK_URL` is set, a `POST` is fired to that URL every time a term's lifecycle status changes:

```powershell
$env:ONTOBRIDGE_WEBHOOK_URL = "https://catalog.company.com/hooks/ontobridge"
$env:ONTOBRIDGE_WEBHOOK_SECRET = "shared-secret"   # optional HMAC signing
```

Payload:
```json
{
  "event": "term.published",
  "timestamp": "2026-05-22T10:30:00Z",
  "term": {
    "uri": "http://ontobridge.dev/ontology/bank/Mortgage",
    "label": "Mortgage",
    "status": "published",
    "definition": "A loan secured by real property...",
    "scheme": "Product",
    "approved_by": "alice",
    "alt_labels": ["Home Loan"],
    "fibo_uri": "https://spec.edmcouncil.org/fibo/..."
  }
}
```

Delivery is non-blocking (background thread). Failures are logged but never crash the API.

### Paginated term list

All list endpoints return a `PagedResponse` envelope:

```
GET /api/terms?limit=100&offset=0
→ { "items": [...], "total": 450, "limit": 100, "offset": 0 }
```

Max `limit` is 500. Works on `/api/terms` and `/api/audit`.

---

## MCP server

OntoBridge exposes an MCP (Model Context Protocol) server so any MCP-compatible client (Claude desktop, Claude Code, Dawiso, etc.) can query and govern terms directly.

### Install

```bash
pip install -e ".[mcp]"
```

### Run

```bash
$env:ONTOBRIDGE_URL = "http://localhost:8001"   # or your shared server IP
python mcp_server.py
```

### Connect from Claude desktop

Add to `~/.claude/claude_desktop_config.json` (adjust path to match your machine):

```json
{
  "mcpServers": {
    "ontobridge": {
      "command": "python",
      "args": ["C:/path/to/ontobridge/mcp_server.py"],
      "env": { "ONTOBRIDGE_URL": "http://localhost:8001" }
    }
  }
}
```

### Connect from Claude Code

Already configured in `.claude/settings.json` — works automatically when the `ontobridge/` folder is open in Claude Code with the server running.

### Available tools

| Tool | Description |
|---|---|
| `get_stats()` | Glossary overview — totals, status breakdown, definition coverage |
| `search_glossary(query, status?)` | Find terms by label or definition text |
| `get_term(uri)` | Full term detail — definition, taxonomy breadcrumb, relations, governance |
| `list_inbox(severity?)` | Terms awaiting steward review |
| `approve_term(uri, actor)` | Publish a term |
| `transition_term(uri, new_status, actor?)` | Move to any lifecycle status |
| `submit_text(text, doc_name?, use_llm?)` | Run the pipeline on a block of text |
| `edit_definition(uri, definition, actor?)` | Rewrite a term definition |
| `get_taxonomy_concepts(scheme?)` | List ontology concepts |
| `get_known_verbs()` | List valid semantic relation verbs |

> **Deployment note:** Set `ONTOBRIDGE_URL` to wherever the API is hosted (defaults to `http://localhost:8001`) — no code changes needed.

---

## How the pipeline works

```
Document
   |
   v
HarvesterAgent        reads PDF/TXT/DOCX, splits into records
   |
   v
NER Extractor         PatternTermExtractor or LLMNerExtractor
   |                  (extraction is independent of FIBO)
   v
FiboMatcher           matches against FIBO labels/synonyms/abbreviations
   |                  adds: closeMatch URI, alt labels, broader concept,
   |                  module, expected definition
   v
MappingAgent          checks for duplicates against ontology concepts
   |                  AND already-published terms (cross-document dedup)
   v
TaxonomyAgent         broader-concept placement via FIBO hierarchy (falls
   |                  back to TF-IDF ontology similarity); the scheme is
   |                  classified by meaning via the LLM into one of the
   |                  ontology's concept schemes
   v
DefinitionAgent       heuristic sentence scoring + optional LLM rewrite
   |                  (LLM also generates IF/THEN business rules)
   v
RelationsAgent        SVO regex extraction from definition text
   |                  + FIBO skos:closeMatch injection
   v
Object resolution     links relation object phrases to published term URIs
   |
   v
GovernanceAgent       evaluates 14 rules → recommended action + confidence
   |
   v
TermPublisher         persists to in-memory store or SQLite
```

---

## Governance rules

| Rule | Category | Severity | Description |
|---|---|---|---|
| R01 | Matching | BLOCK | Exact preferred label match — likely duplicate |
| R02 | Matching | WARN | Acronym expansion matches existing term |
| R03 | Matching | WARN | Fuzzy label match above threshold |
| R04 | Naming | BLOCK | User-rejected synonym resubmitted |
| R05 | Naming | INFO | Cross-domain compatible match |
| R06 | Naming | WARN | Uppercase short label with no context |
| R07 | Naming | WARN | Single noun with no domain qualifier |
| R08 | Quality | BLOCK | Definition shorter than 10 words |
| R09 | Quality | BLOCK | Circular definition (contains the term label) |
| R10 | Quality | BLOCK | No policy source linked |
| R11 | Quality | WARN | Definition found in multiple policy documents |
| R12 | Conflict | WARN | FIBO match with materially divergent definition |
| R13 | Conflict | WARN | Match against a deprecated term |
| R14 | Conflict | BLOCK/WARN | Same label in another domain with incompatible definition |

---

## Steward editing

Every term detail page exposes inline editing:

| Section | What you can do |
|---|---|
| **Definition** | Click Edit → textarea → Save |
| **Also known as** | Add alt labels (type + Enter), remove with × |
| **Taxonomy** | Override → searchable list of ontology concepts → pick broader concept |
| **Semantic relations** | Edit → × remove, add new (verb autocomplete + object label) |

All edits are recorded in the Audit Log with steward name and timestamp.

---

## Project structure

```
ontobridge/
├── src/ontobridge/
│   ├── agents/
│   │   ├── harvester/       # Document ingestion and term extraction
│   │   ├── ner/             # NER extractors (pattern-based + LLM)
│   │   ├── definition/      # Definition extraction and LLM enrichment
│   │   ├── fibo/            # FIBO ontology loader, index, matcher
│   │   ├── taxonomy/        # SKOS taxonomy placement + scheme classification
│   │   ├── relations/       # SVO semantic relation extraction
│   │   ├── governance/      # 14 governance rules (5-state lifecycle)
│   │   ├── policy_linker/   # TF-IDF and vector similarity to policies
│   │   └── mapping/         # Ontology mapping strategies (TF-IDF encoder)
│   ├── audit/               # Audit log (in-memory and SQLite)
│   ├── publisher/           # Term storage (in-memory and SQLite)
│   ├── models/              # Data models (EnrichedTerm, FIBOMatch, ...)
│   ├── batch.py             # BatchPipelineRunner
│   └── pipeline.py          # Single-term PipelineRunner
├── frontend/                # React + Vite production UI
│   └── src/
│       ├── pages/           # Inbox, Glossary, TermDetail, Pipeline, ...
│       └── components/      # Sidebar, TopBar, shared components
├── ontology/
│   └── ontobridge_ontology_v0.1.ttl   # SKOS/OWL ontology (110 concepts, 10 schemes)
├── tests/                   # 779 tests (~65 need optional NLP/embedding packages)
├── mcp_server.py            # MCP server (fastmcp, STDIO/SSE)
└── api_server.py            # FastAPI entry point
```

### What is NOT in the repository (gitignored)

| Path | Why |
|---|---|
| `ontology/fibo/`, `../fibo/` | FIBO is 299 TTL files, cloned separately (see FIBO section above) |
| `ontobridge.db`, `*.db` | SQLite publisher database — local state, not shared via git |
| `frontend/dist/` | Built frontend output — run `npm run build` after clone |
| `frontend/node_modules/` | Node.js packages — run `npm install` after clone |
| `.venv/` | Python virtual environment — recreate with `python -m venv .venv` |

---

## Dashboard pages

| Page | Description |
|---|---|
| **Governance Inbox** | Review terms with severity, confidence, age, governance issues |
| **Run Pipeline** | Upload document, configure LLM, run extraction |
| **Term Detail** | Definition, alt labels, taxonomy override, semantic relations, lifecycle transitions |
| **Glossary** | Browse published terms, filter by scheme/approver/version, export CSV, and publish each term to an external glossary (Dawiso) |
| **Pipeline Stats** | Extraction and governance metrics by scheme |
| **Audit Log** | Full history of all governance actions |
