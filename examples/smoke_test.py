"""Smoke test — run the full pipeline on a real document and report diagnostics."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.batch import BatchPipelineRunner
from ontobridge.publisher import InMemoryPublisher

_ONTOLOGY = Path(__file__).resolve().parents[1] / "ontology" / "ontobridge_ontology_v0.1.ttl"
_DOC = Path(r"c:\SKOLA\DATA PROJEKT\kb-identification-and-verification-of-clients.pdf")


def main() -> None:
    print("\nOntoBridge — Smoke Test")
    print("=" * 60)
    print(f"Document: {_DOC.name}")

    ontology = OntologyIndex.from_file(_ONTOLOGY)
    publisher = InMemoryPublisher()
    batch = BatchPipelineRunner(ontology, publisher)

    result = batch.run_document(_DOC, source_system="smoke_test")

    all_terms = publisher.search_terms("")
    print(f"\nHarvested & processed: {len(all_terms)} terms")
    print(f"Published:  {len(result.published)}")
    print(f"Skipped:    {len(result.skipped)}")
    print(f"Failed:     {len(result.failed)}")

    # --- definition source breakdown ---
    def_sources = Counter(
        t.enriched_term.definition_source for t in all_terms
    )
    print("\nDefinition source:")
    for src, n in sorted(def_sources.items()):
        pct = 100 * n / max(len(all_terms), 1)
        print(f"  {src:<12} {n:>3}  ({pct:.0f}%)")

    # --- governance action breakdown ---
    gov_actions = Counter()
    for t in all_terms:
        gov = t.enriched_term.governance_result
        gov_actions[gov.recommended_action if gov else "none"] += 1
    print("\nGovernance verdict:")
    for action, n in sorted(gov_actions.items()):
        print(f"  {action:<12} {n:>3}")

    # --- terms with no definition ---
    no_def = [
        t for t in all_terms
        if not (t.enriched_term.definition or "").strip()
    ]
    print(f"\nTerms with empty definition: {len(no_def)}")
    for t in no_def[:10]:
        print(f"  - {t.enriched_term.preferred_label}")

    # --- skipped (dedup/governance) ---
    if result.skipped:
        print(f"\nSkipped sample (first 10):")
        for term, reason in result.skipped[:10]:
            print(f"  - {term.preferred_label or '?':<30} {reason[:60]}")

    # --- blocked terms ---
    blocked = [
        t for t in all_terms
        if (t.enriched_term.governance_result and
            t.enriched_term.governance_result.recommended_action == "block")
    ]
    if blocked:
        print(f"\nBlocked terms ({len(blocked)}):")
        for t in blocked[:10]:
            gov = t.enriched_term.governance_result
            flags = ", ".join(gov.blocking_flags) if gov else ""
            print(f"  - {t.enriched_term.preferred_label:<30} [{flags}]")

    # --- all published terms ---
    print(f"\nAll terms ({len(all_terms)}):")
    for t in sorted(all_terms, key=lambda x: x.enriched_term.preferred_label or ""):
        et = t.enriched_term
        gov = et.governance_result
        action = gov.recommended_action if gov else "-"
        tp = et.taxonomy_placement
        scheme = ""
        if tp and tp.scheme_uri:
            seg = tp.scheme_uri.rstrip("/").rsplit("/", 1)[-1]
            scheme = seg.removesuffix("Scheme").removeprefix("Scheme")
        src = et.definition_source or "document"
        defn = (et.definition or "")[:60].replace("\n", " ")
        print(f"  [{action:<7}] [{src:<8}] [{scheme:<12}] {et.preferred_label}")
        if defn:
            print(f"             def: {defn}")

    print("\n" + "=" * 60)
    print("Smoke test complete.")


if __name__ == "__main__":
    main()
