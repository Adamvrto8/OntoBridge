"""Diagnose what the harvester sees in a real document."""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ontobridge.agents.harvester.readers.pdf import PdfReader
from ontobridge.agents.harvester.extractors.pattern import PatternTermExtractor

_DOC = Path(r"c:\SKOLA\DATA PROJEKT\kb-identification-and-verification-of-clients.pdf")


def main() -> None:
    print("=== RAW TEXT (first 3000 chars) ===\n")
    reader = PdfReader()
    docs = list(reader.read(_DOC))
    print(f"Pages/chunks read: {len(docs)}")
    if docs:
        sample = docs[0].text[:3000]
        print(sample)

    print("\n\n=== ALL EXTRACTED TERMS ===\n")
    extractor = PatternTermExtractor()
    all_records = []
    for doc in docs:
        records = extractor.extract(doc)
        all_records.extend(records)

    print(f"Total records extracted: {len(all_records)}")
    for r in all_records:
        label = r.candidate_labels[0].text if r.candidate_labels else "?"
        defn = (r.text or "")[:100].replace("\n", " ")
        print(f"  TERM: {label}")
        print(f"  DEF:  {defn}")
        print()

    print("\n=== SAMPLE SENTENCES (first 50) ===\n")
    from ontobridge.agents.definition.extractor import HeuristicDefinitionExtractor
    hde = HeuristicDefinitionExtractor()
    if docs:
        sentences = hde._split_sentences(docs[0].text)
        for s in sentences[:50]:
            print(f"  | {s[:120]}")


if __name__ == "__main__":
    main()
