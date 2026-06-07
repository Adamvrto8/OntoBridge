# OntoBridge Feedback Knowledge Base

Systém pro sběr a využití zpětné vazby od stewardů k postupnému zlepšování výstupů AI agentů.

---

## Proč to existuje

LLM agenti v pipeline produkují nedeterministické výstupy — definice, relace, doporučení. Steward tyto výstupy opravuje ručně přes UI. Bez tohoto systému každá oprava zmizí a příštím průchodem pipeline produkuje stejné chyby.

**Cíl:** Každá steward oprava se uloží a při příštím průchodu pipeline se automaticky vloží do LLM promptu jako příklad správného výstupu (few-shot learning).

---

## Architektura

```
Steward akce v UI
    │
    ▼
PATCH /api/terms/{uri}/edit          PATCH /api/terms/{uri}/relations
    │  (definice, taxonomie)               │  (schválení / zamítnutí)
    │                                      │
    └──────────────┬───────────────────────┘
                   │
                   ▼
            FeedbackStore  ◄──── app.state.feedback_store
         (ukládá before/after)
                   │
         ┌─────────┴──────────┐
         │                    │
  InMemoryFeedbackStore  SqliteFeedbackStore
  (demo režim)           (DB_PATH režim → *_feedback.db)
                   │
                   ▼
    Při dalším průchodu pipeline:
         │
    ┌────┴────────────────────────┐
    │                             │
    ▼                             ▼
LLMDefinitionAgent          RelationsAgent (LLM stage)
  few-shot: opravy definic     few-shot: schválené/zamítnuté relace
```

---

## Typy událostí

| event_type | Kdy vznikne | old_value | new_value |
|---|---|---|---|
| `definition_corrected` | Steward přepíše definici | původní text | opravený text |
| `taxonomy_corrected` | Steward změní broader concept | původní URI | nové URI |
| `relation_approved` | Steward schválí navrženou relaci | `""` | `"verb → object"` |
| `relation_rejected` | Steward zamítne navrženou relaci | `"verb → object"` | `""` |

---

## Datový model

```python
@dataclass
class FeedbackEvent:
    event_type: str      # viz tabulka výše
    term_label: str      # "Mortgage Loan"
    old_value: str       # co agent vygeneroval
    new_value: str       # co steward opravil
    actor: str           # "steward.alice"
    term_uri: str        # "http://ontobridge.dev/ontology/bank/MortgageLoan"
    timestamp: datetime  # UTC
```

---

## Jak se feedback vkládá do promptů

### LLMDefinitionAgent

Při generování definice agent načte posledních 3–5 oprav a vloží je do promptu:

```
Past steward corrections (use as style guide):
  "Mortgage Loan": agent wrote "A loan for buying property." 
                 → steward corrected to "A credit product secured by real estate..."
  "Credit Risk":  agent wrote "The chance of default." 
                 → steward corrected to "The risk that a borrower will fail..."
```

LLM si z těchto příkladů odvodí požadovaný styl — délku, terminologii, formát.

### RelationsAgent (LLM stage)

Schválené relace se vloží jako pozitivní příklady, zamítnuté jako negativní:

```
Steward-approved relations (these types are valued):
  "Mortgage Loan" → secures → Property
  "Credit Risk" → affects → Lender

Steward-rejected relations (avoid proposing these types):
  "Document" → contains → information relevant to banking operations
```

---

## Klíčové soubory

| Soubor | Popis |
|---|---|
| `src/ontobridge/feedback/models.py` | `FeedbackEvent` dataclass |
| `src/ontobridge/feedback/base.py` | Abstraktní `FeedbackStore` (ABC) |
| `src/ontobridge/feedback/memory.py` | `InMemoryFeedbackStore` — výchozí (demo režim) |
| `src/ontobridge/feedback/sqlite.py` | `SqliteFeedbackStore` — perzistentní (SQLite) |
| `src/ontobridge/api/main.py` | Inicializace `app.state.feedback_store` |
| `src/ontobridge/api/deps.py` | `FeedbackStoreDep` pro dependency injection |
| `src/ontobridge/api/routers/terms.py` | Hooky v `PATCH /edit` a `PATCH /relations` |
| `src/ontobridge/agents/definition/prompt.py` | `build_user_prompt(term, examples=...)` |
| `src/ontobridge/agents/definition/agent.py` | `LLMDefinitionAgent(backend, feedback_store=...)` |
| `src/ontobridge/agents/relations/agent.py` | `RelationsAgent(..., feedback_store=...)` |
| `src/ontobridge/agents/relations/fibo_prompt.py` | `build_user_prompt(..., approved=..., rejected=...)` |

---

## Spuštění

### Demo režim (in-memory, bez perzistence)
```powershell
uvicorn api_server:app
```
Feedback se ukládá jen do paměti — zmizí po restartu.

### Perzistentní režim
```powershell
$env:DB_PATH = "ontobridge.db"
uvicorn api_server:app
```
Feedback se ukládá do `ontobridge_feedback.db` (SQLite). Přežije restart serveru.

---

## Omezení a plánovaná rozšíření

### Aktuální omezení

- **Feedback se nepoužívá pro TaxonomyAgent** — ten je deterministický (similarity scoring), ne LLM-based. Viz sekci níže.
- **Feedback ovlivňuje jen LLM agenty** (`LLMDefinitionAgent`, `RelationsAgent` s LLM backendem).
- **Žádná de-duplikace** — stejný termín lze opravit vícekrát, v promptu se zobrazí jen nejnovější záznamy.
- **Žádná sémantická podobnost při výběru příkladů** — get_examples vrací posledních N záznamů daného typu, ne nejrelevantnější k aktuálnímu termínu.

### Možná budoucí rozšíření

| Vylepšení | Popis | Složitost |
|---|---|---|
| Sémantický výběr příkladů | Místo posledních N záznamů vybrat embeddings-podobné k aktuálnímu termínu | střední |
| Feedback statistiky | Endpoint `GET /api/feedback/stats` — kolik oprav, které termíny nejčastěji | nízká |
| Export pro fine-tuning | `GET /api/feedback/export` — formát JSONL pro případný fine-tuning modelu | nízká |

---

## TaxonomyAgent — přehled a vylepšení

### Jak funguje

`TaxonomyAgent.apply()` prochází tři vrstvy priority:

```
1. Taxonomy overrides (ontology/taxonomy_overrides.json)
        ↓ nenalezeno
2. FIBO hierarchie (term.fibo_match.broader_uri)
        ↓ žádný FIBO match
3. Similarity algoritmus s penalizací délky
```

### 1. Taxonomy overrides

Soubor `ontology/taxonomy_overrides.json` — ručně udržovaný seznam správných parent-child párů. Agent ho načte při startu a zkontroluje jako první, před jakýmkoli algoritmem.

**Formát:**
```json
{
  "Corporate customer": "http://ontobridge.dev/ontology/bank/Customer",
  "Credit card":        "http://ontobridge.dev/ontology/bank/CreditProduct"
}
```

**Jak přidat nový záznam:** Stačí přidat řádek do souboru. Změna se projeví po restartu serveru. Kód se nemění.

Aktuálně obsahuje 25 párů pokrývající zákazníky, produkty, dokumenty, kanály, regulace, organisaci a IT systémy.

### 2. FIBO hierarchie

Pokud FiboMatcher (spuštěný dříve v pipeline) přiřadil termínu `fibo_match` s `broader_uri`, TaxonomyAgent tuto FIBO hierarchii použije přímo (confidence 0.95). FIBO index obsahuje 16 409 tříd a pokrývá hlavní finanční koncepty (FBC, LOAN, FND, SEC...).

Tato cesta funguje automaticky — nevyžaduje žádnou ruční konfiguraci.

### 3. Similarity algoritmus s penalizací délky

Záložní cesta, spustí se pouze pokud termín nemá override ani FIBO match.

**Kořenová příčina původního problému (před opravou):** Agent měřil token overlap symetricky a vybíral nejpodobnější label v ontologii — ale ten byl často sourozenec nebo potomek (např. "Interest Rate" → "Fixed interest rate").

**Oprava:** Do `_rank_parents` přidána penalizace:
- Pokud jsou tokeny dotazovaného labelu podmnožinou tokenů kandidáta (kandidát je pravděpodobně potomek) → skóre × 0.25
- Mírná penalizace za každé extra slovo nad 2 → preferuje kratší, obecnější labely

### Výsledky testování

| Stav | Přesnost (golden dataset, 14 párů) |
|---|---|
| Před opravou (bez FIBO, bez overrides) | **14 %** (2/14) |
| Po opravě (overrides + penalizace délky) | **100 %** (14/14) |

Viz `tests/test_golden_taxonomy.py` pro kompletní golden dataset a přesná očekávání.

### FIBO stav

FIBO ontologie je naklonována v `ontology/fibo/` (297 `.rdf` souborů, 16 409 tříd). Načítá se automaticky při startu serveru — výstup `FIBO index ready.` potvrzuje úspěšné načtení. Varování o datech (`Invalid isoformat string`) jsou kosmetická a neblokují načítání.
