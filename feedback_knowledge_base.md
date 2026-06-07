# OntoBridge Feedback Knowledge Base

System for collecting and applying steward feedback to progressively improve AI agent outputs.

---

## Why it exists

LLM agents in the pipeline produce non-deterministic outputs — definitions, relations, recommendations. Stewards correct these manually through the UI. Without this system, every correction is lost and the pipeline makes the same mistakes on the next run.

**Goal:** Every steward correction is stored and automatically injected into the LLM prompt as a worked example (few-shot learning) on the next pipeline run.

---

## Architecture

```
Steward action in UI
    │
    ▼
PATCH /api/terms/{uri}/edit          PATCH /api/terms/{uri}/relations
    │  (definition, taxonomy)              │  (approve / reject)
    │                                      │
    └──────────────┬───────────────────────┘
                   │
                   ▼
            FeedbackStore  ◄──── app.state.feedback_store
         (stores before/after)
                   │
         ┌─────────┴──────────┐
         │                    │
  InMemoryFeedbackStore  SqliteFeedbackStore
  (demo mode)            (DB_PATH mode → *_feedback.db)
                   │
                   ▼
    On the next pipeline run:
         │
    ┌────┴────────────────────────┐
    │                             │
    ▼                             ▼
LLMDefinitionAgent          RelationsAgent (LLM stage)
  few-shot: definition fixes   few-shot: approved/rejected relations
```

---

## Event types

| event_type | When created | old_value | new_value |
|---|---|---|---|
| `definition_corrected` | Steward rewrites a definition | original text | corrected text |
| `taxonomy_corrected` | Steward changes the broader concept | old URI | new URI |
| `relation_approved` | Steward approves a proposed relation | `""` | `"verb → object"` |
| `relation_rejected` | Steward rejects a proposed relation | `"verb → object"` | `""` |

---

## Data model

```python
@dataclass
class FeedbackEvent:
    event_type: str      # see table above
    term_label: str      # "Mortgage Loan"
    old_value: str       # what the agent generated
    new_value: str       # what the steward corrected it to
    actor: str           # "steward.alice"
    term_uri: str        # "http://ontobridge.dev/ontology/bank/MortgageLoan"
    timestamp: datetime  # UTC
```

---

## How feedback is injected into prompts

### LLMDefinitionAgent

When generating a definition, the agent fetches the last 3–5 corrections and injects them into the prompt:

```
Past steward corrections (use as style guide):
  "Mortgage Loan": agent wrote "A loan for buying property."
                 → steward corrected to "A credit product secured by real estate..."
  "Credit Risk":  agent wrote "The chance of default."
                 → steward corrected to "The risk that a borrower will fail..."
```

The LLM infers the expected style — length, terminology, format — from these examples.

### RelationsAgent (LLM stage)

Approved relations are injected as positive examples, rejected ones as negative:

```
Steward-approved relations (these types are valued):
  "Mortgage Loan" → secures → Property
  "Credit Risk" → affects → Lender

Steward-rejected relations (avoid proposing these types):
  "Document" → contains → information relevant to banking operations
```

---

## Key files

| File | Description |
|---|---|
| `src/ontobridge/feedback/models.py` | `FeedbackEvent` dataclass |
| `src/ontobridge/feedback/base.py` | Abstract `FeedbackStore` (ABC) |
| `src/ontobridge/feedback/memory.py` | `InMemoryFeedbackStore` — default (demo mode) |
| `src/ontobridge/feedback/sqlite.py` | `SqliteFeedbackStore` — persistent (SQLite) |
| `src/ontobridge/api/main.py` | Initialises `app.state.feedback_store` |
| `src/ontobridge/api/deps.py` | `FeedbackStoreDep` for dependency injection |
| `src/ontobridge/api/routers/terms.py` | Hooks in `PATCH /edit` and `PATCH /relations` |
| `src/ontobridge/agents/definition/prompt.py` | `build_user_prompt(term, examples=...)` |
| `src/ontobridge/agents/definition/agent.py` | `LLMDefinitionAgent(backend, feedback_store=...)` |
| `src/ontobridge/agents/relations/agent.py` | `RelationsAgent(..., feedback_store=...)` |
| `src/ontobridge/agents/relations/fibo_prompt.py` | `build_user_prompt(..., approved=..., rejected=...)` |

---

## Running the server

### Demo mode (in-memory, no persistence)
```powershell
uvicorn api_server:app
```
Feedback is stored in memory only — lost on restart.

### Persistent mode
```powershell
$env:DB_PATH = "ontobridge.db"
uvicorn api_server:app
```
Feedback is written to `ontobridge_feedback.db` (SQLite) and survives restarts.

---

## Limitations and planned improvements

### Current limitations

- **Feedback is not used by TaxonomyAgent** — it is deterministic (similarity scoring + overrides), not LLM-based.
- **Feedback only influences LLM agents** (`LLMDefinitionAgent`, `RelationsAgent` with LLM backend).
- **No deduplication** — the same term can be corrected multiple times; only the most recent N entries appear in the prompt.
- **No semantic similarity when selecting examples** — `get_examples` returns the last N records of a given type, not the most relevant ones to the current term.

### Possible future improvements

| Improvement | Description | Complexity |
|---|---|---|
| Semantic example selection | Use embeddings to pick examples closest to the current term instead of the last N | medium |
| Feedback statistics | `GET /api/feedback/stats` endpoint — correction counts, most-corrected terms | low |
| Fine-tuning export | `GET /api/feedback/export` — JSONL format for potential model fine-tuning | low |

---

## TaxonomyAgent — overview and improvements

### How it works

`TaxonomyAgent.apply()` goes through three priority layers:

```
1. Taxonomy overrides  (ontology/taxonomy_overrides.json)
        ↓ not found
2. FIBO hierarchy  (term.fibo_match.broader_uri)
        ↓ no FIBO match
3. Similarity algorithm with length penalty
```

### 1. Taxonomy overrides

`ontology/taxonomy_overrides.json` — a manually maintained list of correct parent-child pairs. The agent loads it at startup and checks it first, before any algorithm runs.

**Format:**
```json
{
  "Corporate customer": "http://ontobridge.dev/ontology/bank/Customer",
  "Credit card":        "http://ontobridge.dev/ontology/bank/CreditProduct"
}
```

**Adding a new entry:** Add a line to the file. The change takes effect after a server restart. No code changes needed.

Currently contains 25 pairs covering customers, products, documents, channels, regulations, organisation units, and IT systems.

### 2. FIBO hierarchy

If the FiboMatcher (run earlier in the pipeline) assigned a `fibo_match` with a `broader_uri` to the term, TaxonomyAgent uses that FIBO hierarchy directly (confidence 0.95). The FIBO index contains 16,409 classes and covers the main financial concepts (FBC, LOAN, FND, SEC…).

This path is fully automatic — no manual configuration required.

### 3. Similarity algorithm with length penalty

Fallback path, triggered only when the term has neither an override nor a FIBO match.

**Root cause of the original bug (before the fix):** The agent measured token overlap symmetrically and picked the most similar label in the ontology — but that was often a sibling or child concept (e.g. "Interest Rate" → "Fixed interest rate").

**Fix:** Length penalty added to `_rank_parents`:
- If the query label's tokens are a subset of the candidate's tokens (candidate is likely a child) → score × 0.25
- Mild penalty for each extra word beyond 2 → prefers shorter, more general labels

### Test results

| State | Accuracy (golden dataset, 14 pairs) |
|---|---|
| Before fix (no FIBO, no overrides) | **14%** (2/14) |
| After fix (overrides + length penalty) | **100%** (14/14) |

See `tests/test_golden_taxonomy.py` for the full golden dataset and exact expectations.

### FIBO status

The FIBO ontology is cloned at `ontology/fibo/` (297 `.rdf` files, 16,409 classes). It loads automatically at server startup — the message `FIBO index ready.` confirms successful loading. Warnings about dates (`Invalid isoformat string`) are cosmetic and do not block loading.

---

## Test suite

As part of this work, **87 automated tests** were written across two files:

| File | Tests | What it covers |
|---|---|---|
| `tests/test_invariants.py` | 71 | Structural constraints on all pipeline agents — model validation, agent output invariants (GovernanceAgent, TaxonomyAgent, MappingAgent, RelationsAgent) |
| `tests/test_golden_taxonomy.py` | 16 | Golden dataset: ground truth parent-child pairs from the ontology, taxonomy accuracy threshold |

All 87 tests are deterministic and require no API key.

For LLM-based quality evaluation (non-deterministic, requires `ANTHROPIC_API_KEY`), see `tests/eval_llm_judge.py`.
