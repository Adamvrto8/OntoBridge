# OntoBridge

Multi-agent semantic term governance system for retail banking.  
Extracts business terms from documents, maps them onto a SKOS/OWL ontology, and routes them through a human-in-the-loop governance workflow — all from a Streamlit dashboard.

---

## Requirements

- Python 3.10 or newer
- Git

Optional (for local LLM extraction):
- [Ollama](https://ollama.com/) running locally

Optional (for Claude-powered extraction):
- Anthropic API key from [console.anthropic.com](https://console.anthropic.com)

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

### 3. Install the package and dependencies

```bash
pip install -e ".[dashboard,readers,llm]"
```

| Extra | What it adds |
|---|---|
| `dashboard` | Streamlit UI, knowledge graph visualisation |
| `readers` | PDF and Word (.docx) document support |
| `llm` | Ollama-backed LLM extraction (langchain-ollama) |

To also enable the Anthropic API backend:
```bash
pip install anthropic
```

### 4. Run the dashboard

**Demo mode** (in-memory, resets on restart — good for testing):
```bash
streamlit run streamlit_app.py
```

**Persistent mode** (SQLite, data survives restarts):
```bash
streamlit run streamlit_app.py -- --db ontobridge.db
```

Open your browser at **http://localhost:8501**

---

## Using the LLM extractors

### Option A — Anthropic API (Claude)

Set your API key in the terminal before starting the dashboard:

**Windows (PowerShell):**
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-api03-..."
streamlit run streamlit_app.py
```

**macOS / Linux:**
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
streamlit run streamlit_app.py
```

In the dashboard: enable **Use LLM extractor**, select **Anthropic API (Claude)**, choose a model (Haiku is fastest, Sonnet gives better results).

To save the key permanently (Windows):
```powershell
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
```

### Option B — Ollama (local, no API key needed)

1. Install Ollama from [ollama.com](https://ollama.com/)
2. Pull a model:
   ```bash
   ollama pull llama3.2:1b    # small, fast
   ollama pull gemma4:26b     # larger, better results
   ```
3. Start the dashboard — Ollama runs automatically in the background
4. In the dashboard: enable **Use LLM extractor**, select **Ollama (local)**, enter the model name

---

## Running the demo script

A standalone demo that runs the full pipeline without the UI:

```bash
python examples/demo.py
```

This will:
1. Load the ontology
2. Extract terms from `examples/sample_policy.txt`
3. Run them through the governance pipeline
4. Export results to CSV and Turtle (`.ttl`)

Output files are written to `examples/output/`.

---

## Project structure

```
ontobridge/
├── src/ontobridge/
│   ├── agents/
│   │   ├── harvester/       # Document ingestion and term extraction
│   │   ├── ner/             # NER extractors (pattern-based + LLM)
│   │   ├── definition/      # Definition extraction and LLM enrichment
│   │   ├── taxonomy/        # SKOS taxonomy placement
│   │   ├── governance/      # Lifecycle rules (DRAFT -> REVIEW -> PUBLISHED)
│   │   ├── policy_linker/   # Vector similarity to existing policies
│   │   └── mapping/         # Ontology mapping strategies
│   ├── audit/               # Audit log (in-memory and SQLite)
│   ├── dashboard/           # Streamlit UI pages
│   ├── publisher/           # Term storage (in-memory and SQLite)
│   ├── models/              # Data models (BusinessTerm, LifecycleStatus, ...)
│   ├── batch.py             # BatchPipelineRunner
│   └── pipeline.py          # Single-term PipelineRunner
├── ontology/
│   └── ontobridge_ontology_v0.1.ttl   # SKOS/OWL ontology (Turtle)
├── examples/
│   ├── demo.py              # End-to-end demo script
│   └── sample_policy.txt    # Sample banking policy document
├── tests/
└── streamlit_app.py         # Dashboard entry point
```

---

## Dashboard pages

| Page | Description |
|---|---|
| **Governance Inbox** | Review and approve/reject terms in REVIEW status |
| **Run Pipeline** | Upload a document and extract business terms |
| **Term Detail** | View full term record, edit lifecycle, send to review |
| **Glossary Browser** | Browse published terms, filter by scheme, export CSV |
| **Pipeline Stats** | Extraction and governance metrics |
| **Knowledge Graph** | Interactive graph of term relationships |
| **Audit Log** | Full history of all governance actions |
| **Miro Board** | Embedded Miro board for collaborative whiteboarding |

---

## How the pipeline works

```
Document
   |
   v
HarvesterAgent  (reads PDF/TXT/DOCX, splits into records)
   |
   v
NER Extractor   (PatternTermExtractor or LLMNerExtractor)
   |
   v
TaxonomyAgent   (places term in SKOS scheme)
   |
   v
DefinitionAgent (heuristic or LLM-powered definition enrichment)
   |
   v
GovernanceAgent (assigns DRAFT/REVIEW lifecycle status)
   |
   v
TermPublisher   (persists to in-memory store or SQLite)
```

---

## Running tests

```bash
pytest
```
