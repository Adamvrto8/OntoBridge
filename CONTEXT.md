# OntoBridge — Project Context for Claude Code

## What is OntoBridge

OntoBridge is a 9-agent multi-agent system that automatically extracts business terms
from heterogeneous data sources, classifies them into a SKOS taxonomy, generates
bidirectional OWL semantic relations, validates them against 14 governance rules, and
publishes them to a target data catalog.

The core value proposition: **Data Governance as Code**. The pipeline runs in the
background on a schedule. Business users search and find governed terms — they never
see the pipeline. Data stewards only review output (approve/reject), they never feed input.

No existing tool — Collibra, Atlan, Alation, Informatica — does this end-to-end.

---

## Architecture overview

### Data sources (priority order)
1. PDF / Word policy documents — **primary authoritative source**
2. Databricks Unity Catalog (REST API) — table names, column names, descriptions, tags
3. Data Products — Collibra, Atlan, custom catalogs via normalised adapter
4. User Input — conversational API, free-text term proposals

### Pipeline flow
```
Sources → Harvester → NER Agent ──────────────────→ Mapping Agent
                              ↘ Policy Linker ↗

Mapping → Taxonomy Agent → Definition Agent ──────→ Governance → Writer → Term Store
                                          ↘ Relations Agent ↗
```

Two parallel branches:
- Branch 1: NER Agent runs in parallel with Policy Linker
- Branch 2: Definition Agent runs in parallel with Relations Agent

Orchestration: **LangGraph** (directed graph, parallel branches, state management)

---

## The 9 Agents

### Agent 1: Harvester
- Role: Universal adapter — normalises all sources into one format
- Input: Raw data from any of the 4 source types
- Output:
```json
{
  "text": "...",
  "source_type": "pdf | unity_catalog | data_product | user_input",
  "source_ref": "CreditPolicy_v3.pdf#section-2.1",
  "timestamp": "2026-04-22T10:00:00Z"
}
```
- Key detail: Pluggable adapter interface — each source type is a separate adapter class

### Agent 2: NER Agent
- Role: Extracts candidate business terms from normalised text
- Approach: LLM-based extraction with prompts (preferred over spaCy for zero-shot)
- Output: List of candidate terms with confidence scores (0–1)
- Key detail: Fine-tuned spaCy is alternative but needs training data

### Agent 3: Policy Linker (parallel with NER)
- Role: Finds the most relevant policy paragraph for each candidate term
- Approach: Vector search via Chroma or pgvector, embedding cosine similarity
- Output: Most relevant policy paragraph + exact `dct:source` provenance link
- Key detail: If no policy source found → term gets status "awaiting_source" and CANNOT be published (Governance Rule 10)

### Agent 4: Mapping Agent
- Role: Deduplication — checks if term already exists
- Three techniques combined:
  1. String distance: rapidfuzz
  2. Embedding cosine similarity: sentence-transformers
  3. SKOS label matching: SPARQL query against existing prefLabel/altLabel
- Four possible outcomes: `exact_match | fuzzy_match | acronym_match | no_match`
- Key detail: Score combination strategy needs to be defined (weighted average recommended)

### Agent 5: Taxonomy Agent (NEW in spec)
- Role: Places term in SKOS hierarchy
- Approach: Embedding cosine similarity against existing SKOS concepts
- Threshold: >= 0.60 → auto-placement, < 0.60 → escalate to human steward
- Output SKOS properties:
  - `skos:broader` → parent concept URI
  - `skos:narrower` → auto-derived on parent
  - `skos:inScheme` → domain scheme URI
- Domain-prefix naming rule: if user rejects synonym proposal → create term as `Domain.TermName` (e.g. `Retail_PI.GI`)
- Sibling conflict detection: check for similar names at same taxonomy level

### Agent 6: Definition Agent (parallel with Relations)
- Role: Generates plain-language definition and business rules
- Input: Candidate term + policy paragraphs from Policy Linker + Mapping decision
- LLM output:
  1. Plain-language definition (minimum 10 words)
  2. 2–3 IF...THEN business rules
  3. Suggested domain assignment
- Key detail: Only place in pipeline where LLM output quality directly affects final term quality

### Agent 7: Relations Agent (parallel with Definition, NEW in spec)
- Role: Extracts bidirectional semantic relations between concepts
- Pass 1: SVO extraction via spaCy dependency parsing (nsubj/dobj/ROOT) or LLM structured JSON
- Pass 2: Verb normalisation via curated inverse-verb lexicon + LLM fallback
- Output: OWL ObjectProperty pairs with owl:inverseOf

Inverse verb lexicon (seed entries):
```
uses        → isUsedBy
has         → belongsTo
triggers    → isTriggeredBy
processes   → isProcessedBy
includes    → isComponentOf
governs     → isGovernedBy
submits     → isSubmittedBy
owns        → isOwnedBy
assigns     → isAssignedTo
requires    → isRequiredBy
```

Turtle output example:
```turtle
bank:RetailPICustomer bank:submits bank:LoanApplication .
bank:LoanApplication bank:isSubmittedBy bank:RetailPICustomer .
bank:submits owl:inverseOf bank:isSubmittedBy .
```

### Agent 8: Governance Agent
- Role: Validates term against 14 rules — NO LLM, purely deterministic
- The only rule-based agent in the pipeline
- Four rule categories:

**Matching (Rules 1–3):**
1. Exact duplicate → block, propose adding as skos:altLabel
2. Acronym expansion matches existing → propose reuse, set as altLabel
3. Similarity >= 80% → show ranked suggestions, user selects reuse or override

**Naming (Rules 4–7):**
4. User rejects synonym → create with domain prefix: Domain.TermName
5. Same term in another domain with compatible meaning → propose skos:exactMatch
6. All-uppercase <= 5 chars, no definition context → reject, require expansion
7. Single common noun, no domain qualifier → require qualifier before creation

**Quality (Rules 8–11):**
8. Definition < 10 words → flag draft, trigger LLM enrichment, block publish
9. Definition contains term's own prefLabel (circular) → block publish
10. Policy Linker finds no matching section → mark draft, status "awaiting_source", block
11. Same term definition in 2+ distinct policy documents → flag multi-policy, require steward sign-off

**Conflict (Rules 12–14):**
12. Matches FIBO prefLabel but definition diverges → warn steward, require justification, add skos:relatedMatch
13. Matches previously deprecated term → warn, show deprecation reason, propose skos:historyNote
14. Same prefLabel in another domain with incompatible definition → block, enforce domain prefix, add skos:scopeNote

Output: `GovResult` with recommended action, required SKOS properties, blocking flags, status

### Agent 9: Writer Agent
- Role: Assembles final RDF payload and pushes to target catalog
- Assembles: prefLabel, altLabel, definition, business rules, domain, policy source, SKOS URIs, taxonomy links, OWL relation triples, full provenance
- Target: Internal PostgreSQL term store (via FastAPI) — NOT Dawiso directly
- Also supports: Dawiso API, OpenMetadata API, Apache Atlas (pluggable adapter)
- Output format: Turtle RDF (.ttl)

---

## Complete Term Data Model (Turtle RDF)

```turtle
bank:RetailPICustomer
  a skos:Concept ;
  skos:prefLabel "Retail PI Customer"@en ;
  skos:altLabel "PI Customer"@en ;
  skos:definition "A retail bank customer in the Personal Instalment segment..."@en ;
  skos:broader bank:RetailCustomer ;
  skos:inScheme bank:PISegmentScheme ;
  bank:submits bank:LoanApplication ;
  bank:has bank:CreditScore ;
  bank:triggers bank:CreditCheck ;
  skos:relatedMatch fibo-fnd:Party ;
  dct:source <policy:CreditPolicy_v3.pdf#section-2.1> ;
  skos:editorialNote "Generated by OntoBridge pipeline 2026-04-22T10:00:00Z"@en .
```

---

## SKOS/OWL Ontology

Standards used:
- **SKOS** — taxonomy and labelling (prefLabel, altLabel, broader, narrower, inScheme, exactMatch, closeMatch)
- **OWL** — semantic relations (ObjectProperty, inverseOf)
- **FIBO** — Financial Industry Business Ontology — external standard to map against
- **Schema.org** — secondary external mapping

Taxonomy example:
```
Customer (Bank) — skos:topConceptOf
├── Retail Customer (Retail) — skos:broader → Customer
│   ├── Retail PI Customer (PI segment) — skos:broader → Retail Customer
│   └── Retail Micro Customer (Micro UW) — skos:broader → Retail Customer
└── Corporate Customer (Corporate) — skos:broader → Customer
    ├── SME Customer — skos:broader → Corporate Customer
    └── Large Corporate Customer — skos:broader → Corporate Customer
```

Domain color coding for Miro:
- Bank = gray
- Retail = blue
- PI segment = teal
- Micro UW = purple
- Corporate = amber

---

## Internal Architecture (replaces Dawiso)

The team builds their own stack instead of depending on Dawiso:

### PostgreSQL Term Store
- Stores all terms at every lifecycle stage
- Schema: HarvestRecord + EnrichedTerm data models
- Agreed in Week 1 — all agents read/write this schema

### FastAPI Backend
- REST API over the PostgreSQL store
- Every agent interacts with terms via this API
- Writer agent pushes final terms here

### Streamlit Steward Dashboard
- Steward interface for morning review
- Shows: new candidate terms, governance results, taxonomy placement, provenance link
- Embedded Miro board for visual knowledge graph overview
- Lifecycle management: approve / reject / send back

### Lifecycle state machine
```
candidate → draft → review → published → deprecated
```
- Terms with blocking governance flags stay in draft
- Terms with warnings go to review (pending_steward_review)
- Steward approves → published

### Writer Agent Adapter Interface
- Pluggable: write to internal PostgreSQL, Dawiso API, OpenMetadata, Apache Atlas
- Platform-agnostic by design (important for potential startup/acquisition)

---

## Team Roles & Responsibilities

### Person A — Ontology Engineer + Architect (most critical)
Owns:
- SKOS/OWL ontology file (.ttl)
- FIBO and Schema.org mappings
- Inverse verb lexicon
- Miro knowledge graph board
- SPARQL validation queries
- Definition of what a "correct" term looks like
- Governance Agent (Week 4)

Background: Business/IM, semantic web concepts

### Person B — Pipeline Engineer (upstream)
Owns:
- Harvester Agent (all 4 adapters)
- NER Agent
- Policy Linker + vector store setup (Chroma/pgvector)

Background: Data engineering or CS

### Person C — Pipeline Engineer (downstream)
Owns:
- Mapping Agent
- Taxonomy Agent
- Definition Agent
- Relations Agent

Background: CS, NLP and embeddings

### Person D — Semantic Layer Dev + Integration
Owns:
- PostgreSQL schema + FastAPI endpoints
- Writer Agent with adapter interface
- Streamlit steward dashboard with embedded Miro
- Lifecycle state machine
- End-to-end integration testing

Background: CS/fullstack, databases and web UIs

---

## 6-Week Sprint Plan

### Week 1 — Discovery & alignment (all together)
- A: leads domain exploration, maps 15–20 assets to FIBO manually, drafts initial SKOS scheme
- B: connects to Databricks Unity Catalog API, pulls raw metadata dump
- C: reviews policy documents, identifies richest term definition sources
- D: designs PostgreSQL schema, HarvestRecord and EnrichedTerm data models

**Week 1 deliverables (all must sign off):**
1. Agreed data model (HarvestRecord + EnrichedTerm at each pipeline stage)
2. Initial taxonomy sketch (top 2–3 SKOS hierarchy levels)
3. Governance rules list (all 14 rules with pass/fail criteria)

### Week 2 — Ontology layer + parallel infrastructure
- A: builds OWL/SKOS .ttl file, ConceptSchemes, broader/narrower hierarchy (first 10–15 concepts), FIBO/Schema.org exactMatch mappings, inverse verb lexicon, first SPARQL validation queries
- B: builds Harvester adapters (Databricks + document chunker), sets up vector store, indexes first policy documents
- C: starts Mapping Agent (string distance + embedding cosine) using A's initial concepts as mock glossary
- D: stands up PostgreSQL, implements FastAPI endpoints, builds lifecycle state machine

**Critical dependency:** A must deliver mock SKOS .ttl (10+ concepts) to C by end of Week 2

### Week 3 — Ontology continues + agents take shape
- A: finishes ontology, SPARQL validation testing, builds Miro board structure, mid-week shifts to supporting C on Taxonomy Agent placement logic
- B: finishes NER Agent and Policy Linker — by end of W3: raw Databricks metadata in → candidate terms with policy provenance out
- C: builds Taxonomy Agent (using A's ontology), starts Definition Agent
- D: finishes Streamlit dashboard layout, Miro embed, governance inbox, term detail panel — steward can browse (empty) DB

### Week 4 — Pipeline completion + first end-to-end run
- A: writes Governance Agent (14 deterministic rules — fast work, well-defined logic)
- B: finishes remaining Harvester adapters, helps C with Relations Agent
- C: finishes Definition Agent and Relations Agent
- D: builds Writer Agent with adapter interface, connects to PostgreSQL

**Week 4 milestone: first full pipeline run**
Harvester → NER + Policy Linker → Mapping → Taxonomy → Definition + Relations → Governance → Writer → term store
Expected: messy, terms in wrong nodes, weird definitions — that's fine, this is the integration milestone.

### Week 5 — Fix, tune, iterate
- A: reviews pipeline output, adjusts ontology (split/merge concepts, fix taxonomy branches)
- B: tunes NER extraction quality, Policy Linker retrieval relevance
- C: adjusts similarity thresholds in Mapping Agent, fixes taxonomy placement errors
- D: fixes integration bugs, ensures Streamlit displays all fields correctly

Run pipeline repeatedly, compare output against A's manual ground truth from Week 1.
This is where precision, recall, and F1 numbers start forming.

### Week 6 — Evaluation, demo, documentation
- A: finalizes Miro board with governed terms, prepares ontology deliverable
- B + C: write evaluation report (taxonomy placement accuracy, relation extraction F1, governance rule distribution, manual vs automated comparison)
- D: polishes Streamlit demo, prepares live walkthrough
- All: documentation, final presentation

---

## Development Approach

### Parallelism model
- **Week 1:** Sequential — everyone waits for agreed data model
- **Weeks 2–3:** Near-fully parallel — everyone develops locally with mock data
- **Week 4:** Gradual convergence — mocks replaced by real outputs
- **Week 5:** Feedback loops — iterative, team reviews shared pipeline output
- **Week 6:** Integration complete

### Three hard blocking dependencies
1. **Mock HarvestRecord (B → C, end of W1):** JSON file with 5 sample records
2. **Mock SKOS .ttl (A → C, end of W2):** 10+ concepts for Mapping/Taxonomy testing
3. **Functional upstream pipeline (B → C → D, end of W4):** Writer needs real enriched data

### Interface contracts (agree in Week 1)
Every agent has a defined input/output as Python TypedDict or Pydantic model.
As long as interfaces match, implementations can evolve independently.

### Local development stack
```
Python virtualenv
Chroma (local, SQLite backend) — for Policy Linker during development
Ollama (local LLM) — for NER + Definition during development
sentence-transformers — embeddings
rapidfuzz — string distance
rdflib — SKOS/OWL manipulation
spaCy + en_core_web_trf — dependency parsing
LangGraph — agent orchestration
pytest — unit tests per agent
```

### Cloud stack (from Week 5)
```
GCP Cloud Run — agents as services
GCP Cloud SQL (pgvector) — shared vector store
GCP Cloud Storage — PDF document storage
GCP Secret Manager — API keys
GCP Vertex AI — embeddings (free tier during development)
```

### Repository structure
```
ontobridge/
├── agents/
│   ├── harvester.py
│   ├── ner_agent.py
│   ├── policy_linker.py
│   ├── mapping_agent.py
│   ├── taxonomy_agent.py
│   ├── definition_agent.py
│   ├── relations_agent.py
│   ├── governance_agent.py
│   └── writer_agent.py
├── ontology/
│   └── ontobridge.ttl
├── api/
│   └── main.py          # FastAPI
├── dashboard/
│   └── app.py           # Streamlit
├── data/
│   └── mock_harvest.json
├── tests/
│   └── test_*.py
├── pipeline.py           # LangGraph orchestration
└── CONTEXT.md
```

---

## Key Technical Decisions

1. **LangGraph for orchestration** — directed graph, parallel branches, state management between agents
2. **Policy-first** — PDF documents are authoritative source; Unity Catalog is secondary enrichment
3. **Own stack instead of Dawiso** — PostgreSQL + FastAPI + Streamlit replaces external catalog dependency
4. **Pluggable Writer adapter** — platform-agnostic output (Dawiso / OpenMetadata / Apache Atlas)
5. **Governance Agent is rule-based only** — no LLM, fully deterministic, 14 if/else rules
6. **LLM fallback strategy** — spaCy for NER and SVO where possible, LLM where spaCy fails
7. **Threshold 0.60 for Taxonomy auto-placement** — start at 0.75 in practice, calibrate against gold set
8. **Mock-first development** — agreed JSON schemas allow parallel development from Week 1
9. **GCP as cloud platform** — team has experience, free tier covers development phase
10. **Local Ollama during development** — zero API cost, switch to OpenAI/Anthropic for final demo

---

## Miro Board Conventions

Primary artefact for steward review before any term is published.

- **Bold lines** = taxonomy (parent-child), labeled with relation type at midpoint (e.g. "kind of customer")
- **Thin lines with arrowheads at both ends** = semantic relations, forward verb near subject, inverse verb near object
- **Node colors** = domain (Bank=gray, Retail=blue, PI=teal, Micro UW=purple, Corporate=amber)
- **Rectangular cards** = taxonomy nodes (color-coded by domain)
- **Distinct card style** = semantic concept nodes

Minimum 10 terms required on board for final evaluation.

---

## Evaluation Metrics (Week 6)

- % assets correctly mapped (taxonomy placement precision/recall vs. manual gold set)
- Taxonomy placement precision/recall against hand-labelled gold set
- Relation extraction F1 score
- Governance rule pass/fail distribution
- Reduction in blank definitions vs. baseline
- Max 10-page evaluation report

---

## Business Context

**Problem:** 62% of organisations say data governance blocks their AI initiatives (Precisely, 2024). 80% of data team time spent preparing data, not analysing it (Informatica, 2024). Only 30% of enterprise data is considered high-quality (Precisely, 2024). Governance tools are built for data engineers — not for business users.

**ROI argument:** Data steward in Central Europe costs ~€25/hour (SalaryExpert/ERI, 2024). One business term takes ~8 hours of manual work (BigID). 500 terms = €100,000 in steward time. With OntoBridge: 500 approvals × 30 seconds = 4 hours total. Same result, 99% less effort.

**Market:** Metadata management market $11.7B (2024) → $36.4B by 2030, CAGR 20.9% (Grand View Research). BFSI segment alone $8.7B by 2030.

**Exit options:**
- Acquisition by Dawiso (built natively on their API, fills a product gap)
- Independent SaaS (platform-agnostic architecture supports any catalog)
- Unfair advantage: SKOS + OWL + multi-agent governance in one pipeline, no competitor today

---

## Operational Flow

### Phase 1 — One-time setup (human)
- Configure Unity Catalog API connection (endpoint, credentials, catalogs/schemas to scan)
- Upload policy PDFs into vector index watched folder
- Configure adapters for other platforms
- Set pipeline schedule (nightly / weekly / triggered)

### Phase 2 — Automated pipeline (zero humans)
- Harvester pulls fresh metadata from Databricks (new tables, updated columns, new tags)
- Re-indexes new/updated policy documents from watched folder
- Processes user submissions from conversational API
- All 9 agents run in sequence
- Writer Agent pushes fully enriched, governance-checked candidate terms to term store

### Phase 3 — Steward review (minutes/day)
- Steward opens Streamlit dashboard in the morning
- Reviews new candidate terms: sees definition, taxonomy placement, governance results, provenance link
- Most approved in seconds, a few rejected or sent back
- Miro board updated separately, gives visual overview of growing taxonomy and semantic relations

**Key insight:** Steward governs output, not feeding input.

---

## Example Pipeline Run

Input: one paragraph from `CreditPolicy_v3.pdf`, section 2.1:
> "A Retail PI Customer is a natural person holding a Personal Instalment loan product. Upon submitting a loan application exceeding 500,000 CZK, a mandatory credit check is triggered. The customer's gross income serves as the primary eligibility criterion."

Pipeline produces (in ~4 seconds):

| Agent | Output |
|-------|--------|
| Harvester | `{text, source_type: "pdf", source_ref: "CreditPolicy_v3.pdf#section-2.1"}` |
| NER | Retail PI Customer (0.97), Loan Application (0.91), Credit Check (0.88), Gross Income (0.85) |
| Policy Linker | Match: CreditPolicy_v3.pdf §2.1, relevance 0.94 |
| Mapping | fuzzy_match "PI Customer" (0.82) → user decides → no_match |
| Taxonomy | Parent: RetailCustomer (0.89 ≥ 0.60) → auto-placed |
| Definition | Plain-language definition + 2 IF...THEN rules |
| Relations | submits/isSubmittedBy, triggers/isTriggeredBy (2 OWL pairs) |
| Governance | APPROVED + 1 FIBO warning → pending_steward_review |
| Writer | Term written to PostgreSQL, status: pending_steward_review |

---

## What Claude Code Should Know

- The project is in early development — no code exists yet beyond planning
- Start implementation from the data models (HarvestRecord, EnrichedTerm) and the LangGraph pipeline skeleton
- Every agent should be independently testable with mock data
- The Governance Agent is purely deterministic — 14 if/else rules, no ML
- The ontology (.ttl) is Person A's deliverable — code should load it from file, not hardcode concepts
- Python is the primary language throughout
- Use Pydantic models for all inter-agent data transfer
- LangGraph state should carry the full term record through all agents
- The Writer Agent must have an abstract base class with concrete implementations per target catalog
