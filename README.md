# OntoBridge

Multi-agent semantic term governance system for retail banking.  
Extracts business terms from documents, maps them onto a SKOS/OWL ontology, enriches them with FIBO (Financial Industry Business Ontology), and routes them through a human-in-the-loop governance workflow.

Two interfaces are available:
- **React web app** — production UI (FastAPI backend + Vite/React frontend)
- **Streamlit dashboard** — quick prototyping and internal tooling

---

## System requirements

| Tool | Minimum | Notes |
|---|---|---|
| Python | 3.10+ | 3.12+ recommended |
| Node.js | 18+ | For the React frontend |
| Git | any | |

---

## Quick start (minimal — run the app)

### 1. Clone the repository

```bash
git clone https://github.com/Adamvrto8/OntoBridge.git
cd OntoBridge/ontobridge
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -e ".[api,readers,llm]"
```

For Claude API support (needed for LLM extraction with Anthropic models):
```bash
pip install -e ".[api,readers,llm,claude]"
```

### 4. Build and start the React frontend

```bash
cd frontend
npm install
npm run build   # build once; use 'npm run dev' for hot-reload during development
cd ..
```

### 5. Start the FastAPI backend

**Demo mode** (in-memory, resets on restart):
```powershell
python -m uvicorn api_server:app --host 0.0.0.0 --port 8001
```

**Persistent mode** (SQLite, survives restarts):
```powershell
$env:DB_PATH = "ontobridge.db"
python -m uvicorn api_server:app --host 0.0.0.0 --port 8001
```

> **Do not use `--reload`** — FIBO ontology indexing takes 1–3 minutes at startup; `--reload` would re-index on every code change.

Open **http://localhost:8001** in your browser.  
Interactive API docs: **http://localhost:8001/docs**

---

## Full developer install (matches the reference environment — 598 tests)

This is what gives you the same setup as the person who set up the project, including all optional NLP packages needed for the full test suite.

```bash
# 1. Clone and enter the project
git clone https://github.com/Adamvrto8/OntoBridge.git
cd OntoBridge/ontobridge

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate       # macOS / Linux

# 3. Install all Python extras
pip install -e ".[api,readers,llm,claude,dev,embeddings,nlp,mcp]"

# 4. Download the spaCy language model (required for NLP tests and extraction)
python -m spacy download en_core_web_sm

# 5. Install Node.js frontend dependencies
cd frontend && npm install && cd ..

# 6. Verify: full test suite should show 598 collected
pytest --collect-only -q
```

Expected output: `598 tests collected` (40 of those require sentence-transformers + spaCy and are skipped automatically when those packages are not installed).

---

## What each Python extra provides

| Extra | Install command | What it adds |
|---|---|---|
| `api` | included in quick start | FastAPI + Uvicorn REST backend |
| `readers` | included in quick start | PDF and Word (.docx) document support |
| `llm` | included in quick start | Ollama-backed LLM extraction |
| `claude` | `pip install -e ".[claude]"` | Anthropic Claude API support |
| `dev` | full dev install | pytest + sentence-transformers + spaCy |
| `embeddings` | full dev install | `SentenceTransformerEncoder` for dense similarity |
| `nlp` | full dev install | spaCy-based term/SVO extraction |
| `mcp` | full dev install | MCP server (`mcp_server.py`) |
| `vector` | optional | ChromaDB policy linker (replaced by TF-IDF linker by default) |
| `dashboard` | optional | Streamlit UI (`streamlit run streamlit_app.py`) |

---

## Shared team server

Run one instance that the whole team can access over the local network.

### Host machine

```powershell
# Full install (if not already done)
pip install -e ".[api,readers,llm,claude]"
cd frontend && npm install && cd ..

# Start — builds frontend, binds 0.0.0.0, prints LAN IP
.\start_server.ps1 -Port 8001
```

The script prints your LAN address:

```
========================================
  OntoBridge starting on port 8001

  This machine:  http://localhost:8001
  Team members:  http://192.168.1.42:8001   ← share this
  API docs:      http://localhost:8001/docs
========================================
```

Data is stored in `ontobridge.db` (SQLite) and survives restarts.

> **Note:** `ontobridge.db` is listed in `.gitignore` — it is never committed. Each fresh clone starts with an empty database. This is intentional; the production database lives on the host machine only.

### Connecting (team members)

Open **`http://<host-ip>:8001`** in a browser — no install needed on the client side.

### Running a local dev frontend against the shared API

```powershell
# In frontend/
$env:VITE_BACKEND_URL = "http://192.168.1.42:8001"
npm run dev
```

### start_server.ps1 options

| Flag | Effect |
|---|---|
| `.\start_server.ps1 -Port 8001` | Persistent SQLite + builds frontend |
| `.\start_server.ps1 -Port 8001 -NoBuild` | Skip `npm build` (already built) |
| `.\start_server.ps1 -Port 8001 -Demo` | In-memory mode (resets on restart) |

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
- `claude-opus-4-7`

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
# Minimal install (558 tests collected — NLP packages not installed)
pytest

# Full dev install (598 tests collected — includes spaCy + sentence-transformers tests)
pytest

# Single file
pytest tests/test_relations_agent.py -v

# Filter by name
pytest -k "fibo" -v
```

### Test count explained

| Condition | Tests collected | Skipped |
|---|---|---|
| Base install `.[api,readers,llm]` | 558 | 3 (chromadb, spaCy, sentence-transformers) |
| Full dev install `.[dev,embeddings,nlp]` + spaCy model | 598 | 1 (chromadb) |

The 40 extra tests (`test_spacy_extractors.py`, `test_sentence_transformer_encoder.py`) use `pytest.importorskip` — they are silently skipped when those packages are absent, so `pytest` still reports 100% pass rate either way.

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

> **GCP note:** Change `ONTOBRIDGE_URL` to the Cloud Run URL — no code changes needed.

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
MappingAgent          checks for duplicates against existing glossary
   |
   v
TaxonomyAgent         FIBO hierarchy placement (falls back to TF-IDF
   |                  ontology similarity when no FIBO match found)
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
| **Taxonomy** | Override → searchable list of 103 ontology concepts → pick broader concept |
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
│   │   ├── taxonomy/        # SKOS taxonomy placement
│   │   ├── relations/       # SVO semantic relation extraction
│   │   ├── governance/      # 14 lifecycle rules (DRAFT → REVIEW → PUBLISHED)
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
│   └── ontobridge_ontology_v0.1.ttl   # SKOS/OWL ontology (103 concepts, 10 schemes)
├── tests/                   # 598 tests (558 without optional NLP packages)
├── mcp_server.py            # MCP server (fastmcp, STDIO/SSE)
├── api_server.py            # FastAPI entry point
├── start_server.ps1         # Shared team server launcher
└── streamlit_app.py         # Streamlit dashboard (optional)
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
| **Glossary** | Browse published terms, filter by scheme/approver/version, export CSV |
| **Pipeline Stats** | Extraction and governance metrics by scheme |
| **Knowledge Graph** | Force-directed graph of terms and resolved semantic relations |
| **Audit Log** | Full history of all governance actions |
