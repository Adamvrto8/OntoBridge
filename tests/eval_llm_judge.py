"""
LLM-as-judge evaluation for OntoBridge pipeline agents.

Usage:
    python tests/eval_llm_judge.py

Requires:
    ANTHROPIC_API_KEY environment variable (or pass --api-key)

What it does:
    Runs TaxonomyAgent, RelationsAgent, and GovernanceAgent on a set of known
    banking terms, then asks Claude to score each output 1–5 for semantic
    correctness.  Results are printed as a table and saved to
    tests/eval_reports/<timestamp>.json for trend tracking.

This is NOT a pytest test — it is non-deterministic and requires a paid API key.
Run it manually when you want a quality snapshot of agent outputs.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

# Make sure the src/ package is importable when run as a script
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ontobridge.agents.governance import GovernanceAgent
from ontobridge.agents.governance.models import Candidate
from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.agents.mapping import MappingAgent, from_ontology
from ontobridge.agents.relations import RelationsAgent
from ontobridge.agents.taxonomy import TaxonomyAgent
from ontobridge.models.enrichment import CandidateLabel, EnrichedTerm
from ontobridge.models.source import HarvestRecord, SourceRef, SourceType, Tier

ONTOLOGY_PATH = PROJECT_ROOT / "ontology" / "ontobridge_ontology_v0.1.ttl"
REPORTS_DIR = PROJECT_ROOT / "tests" / "eval_reports"

JUDGE_MODEL = "claude-haiku-4-5-20251001"

# How many concepts to sample from the ontology (spread across schemes)
SAMPLE_PER_SCHEME = 1


# ─── Sample terms — loaded from the ontology ──────────────────────────────────

def _load_sample_terms(ontology: OntologyIndex, per_scheme: int = SAMPLE_PER_SCHEME) -> list[dict]:
    """Pick up to `per_scheme` concepts per scheme that have a definition."""
    seen_schemes: dict[str, int] = {}
    result = []
    for c in ontology.concepts:
        if not c.definition:
            continue
        scheme = c.scheme_label or "unknown"
        if seen_schemes.get(scheme, 0) >= per_scheme:
            continue
        seen_schemes[scheme] = seen_schemes.get(scheme, 0) + 1
        result.append({"label": c.pref_label, "definition": c.definition})
    return result


# ─── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class JudgeScore:
    score: int       # 1–5
    reason: str


@dataclass
class TaxonomyEval:
    label: str
    broader_concept: str
    scheme: str
    score: int
    reason: str


@dataclass
class RelationsEval:
    label: str
    relations_count: int
    relations_summary: str
    score: int
    reason: str


@dataclass
class GovernanceEval:
    label: str
    recommended_action: str
    triggered_rules: list[str]
    score: int
    reason: str


@dataclass
class EvalReport:
    timestamp: str
    model: str
    taxonomy: list[TaxonomyEval]
    relations: list[RelationsEval]
    governance: list[GovernanceEval]

    def avg(self, evals: list) -> float:
        if not evals:
            return 0.0
        return round(sum(e.score for e in evals) / len(evals), 2)


# ─── Judge client ─────────────────────────────────────────────────────────────


class Judge:
    """Thin wrapper around the Anthropic API for structured 1-5 scoring."""

    SYSTEM = (
        "You are an expert in banking terminology, ontology design, and data governance. "
        "Your task is to evaluate whether a pipeline agent produced a semantically correct "
        "and useful output for a given banking term. "
        "Always respond ONLY with a valid JSON object in the form: "
        '{"score": <integer 1-5>, "reason": "<one sentence>"}. '
        "1 = completely wrong or useless, 3 = acceptable but improvable, 5 = ideal output."
    )

    def __init__(self, api_key: str, model: str = JUDGE_MODEL):
        try:
            import anthropic
        except ImportError:
            raise ImportError("Install anthropic: pip install anthropic")
        self._client = anthropic.Anthropic(api_key=api_key.strip())
        self._model = model

    def score(self, prompt: str) -> JudgeScore:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=256,
            temperature=0,
            system=self.SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        # Haiku sometimes wraps JSON in markdown code fences — strip them
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        try:
            data = json.loads(raw)
            return JudgeScore(score=int(data["score"]), reason=str(data["reason"]))
        except (json.JSONDecodeError, KeyError, ValueError):
            return JudgeScore(score=0, reason=f"[parse error] {raw[:120]}")


# ─── Helper ───────────────────────────────────────────────────────────────────


def _make_term(label: str, definition: str) -> EnrichedTerm:
    record = HarvestRecord(
        text=definition,
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="eval"),
        tier=Tier.UNSTRUCTURED,
    )
    t = EnrichedTerm.from_harvest(record)
    t.candidate_labels = [CandidateLabel(text=label, confidence=0.95)]
    t.definition = definition
    return t


def _concept_label(ontology: OntologyIndex, uri: str) -> str:
    """Return the pref_label for a concept URI, or the URI tail if not found."""
    for c in ontology.concepts:
        if c.uri == uri:
            return c.pref_label
    return uri.rstrip("/").rsplit("/", 1)[-1]


# ─── Per-agent evaluation ─────────────────────────────────────────────────────


def eval_taxonomy(
    judge: Judge,
    ontology: OntologyIndex,
    terms: list[dict],
) -> list[TaxonomyEval]:
    agent = TaxonomyAgent(ontology)
    results = []

    for t in terms:
        label, definition = t["label"], t["definition"]
        placement = agent.evaluate(_make_term(label, definition))

        if placement.broader_concept_uri:
            broader = _concept_label(ontology, placement.broader_concept_uri)
        else:
            broader = "(none — unresolved)"

        scheme = _concept_label(ontology, placement.scheme_uri) if placement.scheme_uri else "(none)"

        prompt = (
            f'Term: "{label}"\n'
            f'Definition: "{definition}"\n\n'
            f'TaxonomyAgent placed this term under:\n'
            f'  Broader concept: "{broader}"\n'
            f'  Scheme: "{scheme}"\n'
            f'  Confidence: {placement.placement_confidence:.2f}\n\n'
            f"Is this taxonomy placement semantically correct for a banking glossary? "
            f"Consider whether '{broader}' is a sensible parent concept for '{label}'."
        )

        s = judge.score(prompt)
        results.append(TaxonomyEval(
            label=label,
            broader_concept=broader,
            scheme=scheme,
            score=s.score,
            reason=s.reason,
        ))
        print(f"  [{s.score}/5] {label} → {broader}")

    return results


def eval_relations(
    judge: Judge,
    ontology: OntologyIndex,
    terms: list[dict],
) -> list[RelationsEval]:
    agent = RelationsAgent(ontology=ontology)
    results = []

    for t in terms:
        label, definition = t["label"], t["definition"]
        term = _make_term(label, definition)
        agent.apply(term)

        if not term.relations:
            summary = "(no relations extracted)"
        else:
            lines = [
                f'  - "{r.verb}" → "{r.object_label}" [{r.status.value}, confidence={r.confidence:.2f}]'
                for r in term.relations
            ]
            summary = "\n".join(lines)

        prompt = (
            f'Term: "{label}"\n'
            f'Definition: "{definition}"\n\n'
            f"RelationsAgent extracted {len(term.relations)} relation(s):\n"
            f"{summary}\n\n"
            f"Evaluate: are the extracted verbs and objects semantically sensible "
            f"for a banking ontology? Do the relations capture meaningful connections "
            f"this term has to other banking concepts?"
        )

        s = judge.score(prompt)
        results.append(RelationsEval(
            label=label,
            relations_count=len(term.relations),
            relations_summary=summary,
            score=s.score,
            reason=s.reason,
        ))
        print(f"  [{s.score}/5] {label} ({len(term.relations)} relations)")

    return results


def eval_governance(
    judge: Judge,
    ontology: OntologyIndex,
    terms: list[dict],
) -> list[GovernanceEval]:
    agent = GovernanceAgent(ontology=ontology)
    results = []

    for t in terms:
        label, definition = t["label"], t["definition"]
        candidate = Candidate(preferred_label=label, definition=definition)
        result = agent.evaluate(candidate)

        triggered_titles = [f.title for f in result.triggered]

        prompt = (
            f'Term: "{label}"\n'
            f'Definition: "{definition}"\n\n'
            f"GovernanceAgent recommended action: {result.recommended_action.upper()}\n"
            f"Blocking flags: {result.blocking_flags or '(none)'}\n"
            f"Triggered rules ({len(triggered_titles)}): {', '.join(triggered_titles) or '(none)'}\n\n"
            f"Is the recommended action '{result.recommended_action}' appropriate "
            f"for this term and definition in a banking data governance context? "
            f"Consider whether the flagged rules are reasonable."
        )

        s = judge.score(prompt)
        results.append(GovernanceEval(
            label=label,
            recommended_action=result.recommended_action,
            triggered_rules=triggered_titles,
            score=s.score,
            reason=s.reason,
        ))
        print(f"  [{s.score}/5] {label} → {result.recommended_action.upper()} ({len(triggered_titles)} rules)")

    return results


# ─── Report ───────────────────────────────────────────────────────────────────


def print_report(report: EvalReport) -> None:
    sep = "─" * 72
    print(f"\n{'=' * 72}")
    print(f"  OntoBridge LLM-as-Judge Evaluation")
    print(f"  {report.timestamp}   judge: {report.model}")
    print(f"{'=' * 72}")

    def _section(title: str, evals: list, cols: list[tuple[str, int, callable]]) -> None:
        print(f"\n{title}")
        print(sep)
        header = "  ".join(f"{h:<{w}}" for h, w, _ in cols)
        print(header)
        print(sep)
        for e in evals:
            row = "  ".join(f"{fn(e):<{w}}" for _, w, fn in cols)
            print(row)

    _section(
        "TAXONOMY AGENT  (is the parent concept correct?)",
        report.taxonomy,
        [
            ("Term", 22, lambda e: e.label),
            ("Broader concept", 24, lambda e: e.broader_concept),
            ("Score", 6, lambda e: f"{e.score}/5"),
            ("Reason", 40, lambda e: e.reason[:38] + ".." if len(e.reason) > 40 else e.reason),
        ],
    )

    _section(
        "RELATIONS AGENT  (are extracted relations sensible?)",
        report.relations,
        [
            ("Term", 22, lambda e: e.label),
            ("# relations", 12, lambda e: str(e.relations_count)),
            ("Score", 6, lambda e: f"{e.score}/5"),
            ("Reason", 40, lambda e: e.reason[:38] + ".." if len(e.reason) > 40 else e.reason),
        ],
    )

    _section(
        "GOVERNANCE AGENT  (is the recommended action appropriate?)",
        report.governance,
        [
            ("Term", 22, lambda e: e.label),
            ("Action", 10, lambda e: e.recommended_action),
            ("Score", 6, lambda e: f"{e.score}/5"),
            ("Reason", 40, lambda e: e.reason[:38] + ".." if len(e.reason) > 40 else e.reason),
        ],
    )

    print(f"\n{sep}")
    print(
        f"  Averages — "
        f"Taxonomy: {report.avg(report.taxonomy)}/5   "
        f"Relations: {report.avg(report.relations)}/5   "
        f"Governance: {report.avg(report.governance)}/5"
    )
    print(sep)


def save_report(report: EvalReport) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = report.timestamp.replace(":", "-").replace(" ", "_")
    path = REPORTS_DIR / f"eval_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False)
    return path


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        print("Set it with:")
        print("  $env:ANTHROPIC_API_KEY = 'sk-ant-...'   # PowerShell")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'   # bash")
        sys.exit(1)

    print(f"Loading ontology from {ONTOLOGY_PATH} ...")
    ontology = OntologyIndex.from_file(ONTOLOGY_PATH)
    print(f"Ontology loaded ({len(ontology.concepts)} concepts).")

    sample_terms = _load_sample_terms(ontology)
    print(f"Sampled {len(sample_terms)} terms from ontology ({SAMPLE_PER_SCHEME} per scheme):")
    for t in sample_terms:
        print(f"  - {t['label']}")

    judge = Judge(api_key=api_key)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("\n--- TaxonomyAgent evaluation ---")
    taxonomy_evals = eval_taxonomy(judge, ontology, sample_terms)

    print("\n--- RelationsAgent evaluation ---")
    relations_evals = eval_relations(judge, ontology, sample_terms)

    print("\n--- GovernanceAgent evaluation ---")
    governance_evals = eval_governance(judge, ontology, sample_terms)

    report = EvalReport(
        timestamp=ts,
        model=JUDGE_MODEL,
        taxonomy=taxonomy_evals,
        relations=relations_evals,
        governance=governance_evals,
    )

    print_report(report)

    path = save_report(report)
    print(f"\nReport saved to: {path}")


if __name__ == "__main__":
    main()
