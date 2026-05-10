# OntoBridge

Multi-agent semantic term governance system for retail banking.  
Extracts business terms from documents, maps them onto a SKOS/OWL ontology, enriches them with FIBO (Financial Industry Business Ontology), and routes them through a human-in-the-loop governance workflow.

Two interfaces are available:
- **React web app** — production UI (FastAPI backend + Vite/React frontend)
- **Streamlit dashboard** — quick prototyping and internal tooling

---

## Requirements

- Python 3.10 or newer
- Node.js 18 or newer (for the React frontend)
- Git

Optional (for local LLM extraction):
- [Ollama](https://ollama.com/) running locally

Optional (for Claude-powered extraction):
- Anthropic API key from [console.anthropic.com](https://console.anthropic.com)

Optional (for FIBO ontology matching):
- FIBO repository cloned anywhere on disk — auto-detected at `../fibo`, `./fibo`, `./fibo-master`

---

## Quick start

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

| Extra | What it adds |
|---|---|
| `api` | FastAPI + Uvicorn REST backend |
| `dashboard` | Streamlit UI (optional, for internal tooling) |
| `readers` | PDF and Word (.docx) document support |
| `llm` | Ollama-backed LLM extraction |

For Anthropic API support:
```bash
pip install anthropic
```

For FIBO ontology matching:
```bash
pip install rdflib
```

### 4. Start the FastAPI backend

**Demo mode** (in-memory, resets on restart):
```bash
uvicorn api_server:app --reload
```

**Persistent mode** (SQLite, survives restarts):
```powershell
$env:DB_PATH = "ontobridge.db"
uvicorn api_server:app --reload
```

API runs at **http://localhost:8000** · Interactive docs at **http://localhost:8000/docs**

### 5. Start the React frontend

In a second terminal:
```bash
cd frontend
npm install
npm run dev
```

Open your browser at **http://localhost:5173**

---

### Running the Streamlit dashboard (optional)

The original Streamlit dashboard is still available for internal use:

```bash
streamlit run streamlit_app.py
```

Open at **http://localhost:8501**

---

## Using the LLM extractors

The Run Pipeline page exposes two LLM toggles:

- **Use LLM extractor** — replaces the pattern-based NER with a Claude or Ollama model for higher-quality term extraction
- **Improve definitions** — sends each extracted term through the LLM to rewrite its definition and generate IF/THEN business rules

### Option A — Anthropic API (Claude)

In the Run Pipeline page: enable an LLM toggle, select **Anthropic API**, choose a model, and optionally paste your API key directly into the key field. If left blank, the `ANTHROPIC_API_KEY` environment variable is used.

To set the key as an environment variable:

**Windows (PowerShell):**
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-api03-..."
```

To save permanently:
```powershell
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
```

**macOS / Linux:**
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

Available models (fastest → best quality):
- `claude-haiku-4-5-20251001`
- `claude-sonnet-4-6`
- `claude-opus-4-7`

### Option B — Ollama (local, no API key needed)

1. Install Ollama from [ollama.com](https://ollama.com/)
2. Pull a model:
   ```bash
   ollama pull llama3.2:1b    # small, fast
   ollama pull gemma4:26b     # larger, better results
   ```
3. In Run Pipeline: enable an LLM toggle, select **Ollama (local)**, enter the model name

---

## FIBO ontology integration

OntoBridge optionally integrates with the [FIBO](https://spec.edmcouncil.org/fibo/) (Financial Industry Business Ontology) — a standardized ontology covering financial instruments, institutions, and concepts.

### Setup

Clone the FIBO repository anywhere on disk:
```bash
git clone https://github.com/edmcouncil/fibo.git
```

OntoBridge auto-detects it at these locations (checked in order):
- `../fibo` (sibling of the ontobridge folder — recommended)
- `./fibo`
- `./fibo-master`
- `./fibo-master/fibo-master`

No configuration needed. The index loads on the first pipeline run (~30–60 seconds for 299 files) and is cached in memory for all subsequent runs.

### What FIBO adds to each term

| Feature | Description |
|---|---|
| **skos:closeMatch relation** | If a term matches a FIBO concept, a semantic relation linking to the official FIBO URI is added to the term detail |
| **Alt labels** | FIBO synonyms and abbreviations (e.g. "financial institution", "BIC", "AML") are injected as alt labels and appear under "Also known as" |
| **Definition quality check** | Governance Rule 12 compares the extracted definition against FIBO's authoritative definition and warns when they diverge significantly |

Matching works on preferred labels, SKOS alt labels, `cmns-av:synonym` (418 entries), and `cmns-av:abbreviation` (810 entries). Terms like "AML", "BIC", or "financial institution" will match even if the document uses the abbreviated form.

---

## How the pipeline works

```
Document
   |
   v
HarvesterAgent    reads PDF/TXT/DOCX, splits into records
   |
   v
NER Extractor     PatternTermExtractor or LLMNerExtractor
   |
   v
FiboMatcher       matches term against FIBO — adds closeMatch URI,
   |              alt labels, expected definition (optional, needs fibo/)
   v
MappingAgent      checks for duplicates against existing glossary
   |
   v
TaxonomyAgent     places term in SKOS taxonomy scheme
   |
   v
DefinitionAgent   heuristic or LLM-powered definition enrichment
   |              (also generates IF/THEN business rules when LLM enabled)
   v
RelationsAgent    SVO extraction from definition text + FIBO closeMatch
   |
   v
GovernanceAgent   evaluates 14 rules, assigns DRAFT/REVIEW/PUBLISHED
   |
   v
TermPublisher     persists to in-memory store or SQLite
```

---

## Governance rules

The governance engine evaluates 14 rules across three categories:

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
│   │   ├── policy_linker/   # Vector similarity to existing policies
│   │   └── mapping/         # Ontology mapping strategies
│   ├── audit/               # Audit log (in-memory and SQLite)
│   ├── dashboard/           # Streamlit UI pages
│   ├── publisher/           # Term storage (in-memory and SQLite)
│   ├── models/              # Data models (EnrichedTerm, FIBOMatch, ...)
│   ├── batch.py             # BatchPipelineRunner
│   └── pipeline.py          # Single-term PipelineRunner
├── frontend/                # React + Vite production UI
│   └── src/
│       ├── pages/           # Inbox, Glossary, TermDetail, Pipeline, ...
│       └── components/      # Sidebar, TopBar, shared components
├── ontology/
│   └── ontobridge_ontology_v0.1.ttl   # SKOS/OWL ontology (Turtle)
├── examples/
│   ├── demo.py              # End-to-end demo script
│   └── sample_policy.txt    # Sample banking policy document
├── tests/                   # 574 tests, pytest
└── streamlit_app.py         # Streamlit dashboard entry point
```

---

## Dashboard pages

| Page | Description |
|---|---|
| **Governance Inbox** | Review terms with severity, confidence, age, and governance issue details |
| **Run Pipeline** | Upload a document, configure LLM options and API key, run extraction |
| **Term Detail** | Full term record — definition, alt labels, business rules, taxonomy, semantic relations, lifecycle transitions |
| **Glossary** | Browse all published terms, filter by scheme/approver/version, export CSV |
| **Pipeline Stats** | Extraction and governance metrics by scheme |
| **Knowledge Graph** | Interactive graph of term relationships |
| **Audit Log** | Full history of all governance actions |
| **Miro Board** | Embedded Miro board for collaborative whiteboarding |

---

## Running tests

```bash
pytest
```

574 tests, 1 skipped (chromadb optional dependency).
