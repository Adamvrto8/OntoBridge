from __future__ import annotations

import re

from ontobridge.agents.harvester.protocols import ExtractedTerm, RawDocument

# ---------------------------------------------------------------------------
# Definition trigger patterns for banking policy documents
# ---------------------------------------------------------------------------
# Each pattern must have exactly two named groups: (?P<term>...) and (?P<def>...)
# They are tried in order; the first match on a paragraph wins.

_DEFINITION_PATTERNS: list[tuple[str, float]] = [
    # "Term" means / shall mean / is defined as / refers to DEFINITION.
    (
        r'["“‘]?(?P<term>[A-Z][A-Za-z0-9 \-/]{1,60})["”’]?'
        r'\s+(?:means|shall mean|is defined as|refers to|is understood as|denotes)\s+'
        r'(?P<def>[A-Za-z][^\n]{20,})',
        0.90,
    ),
    # TERM: DEFINITION  (glossary / catalog style)
    (
        r'^(?P<term>[A-Z][A-Za-z0-9 \-/]{1,60}):\s+(?P<def>[A-Z][^\n]{20,})',
        0.85,
    ),
    # "TERM" – DEFINITION  (em-dash / en-dash separator)
    (
        r'["“‘](?P<term>[A-Z][A-Za-z0-9 \-/]{1,60})["”’]'
        r'\s*[–—\-]\s*(?P<def>[A-Za-z][^\n]{20,})',
        0.80,
    ),
    # TERM (acronym): DEFINITION — "KYC (Know Your Customer): ..."
    (
        r'^(?P<term>[A-Z][A-Za-z0-9 \-/]{1,50}\s*\([^)]{2,30}\)):\s+'
        r'(?P<def>[A-Za-z][^\n]{20,})',
        0.85,
    ),
]

_COMPILED: list[tuple[re.Pattern[str], float]] = [
    (re.compile(pat, re.MULTILINE), conf)
    for pat, conf in _DEFINITION_PATTERNS
]

# Minimum definition word count — anything shorter is noise
_MIN_DEF_WORDS = 8

# Maximum label word count — longer than this is a sentence, not a term name
_MAX_LABEL_WORDS = 7

# Labels starting with these words are sentence fragments, not term names
_SENTENCE_STARTERS = {
    "this", "the", "a", "an", "these", "those", "that",
    "it", "its", "they", "their", "we", "our", "all", "each",
}


class PatternTermExtractor:
    """Extracts (term, definition) pairs from a RawDocument using regex heuristics.

    Designed for banking policy documents and catalog descriptions that follow
    common glossary conventions.  Plug in a spaCy-based extractor later via the
    ``TermExtractor`` protocol without touching any other code.
    """

    def extract(self, doc: RawDocument) -> list[ExtractedTerm]:
        results: list[ExtractedTerm] = []
        seen_labels: set[str] = set()

        # Try the whole paragraph text first
        for para in _split_sentences(doc.text):
            for pattern, confidence in _COMPILED:
                m = pattern.search(para)
                if not m:
                    continue
                label = _clean_label(m.group("term"))
                definition = _clean_definition(m.group("def"))
                if not _is_valid(label, definition):
                    continue
                key = label.casefold()
                if key in seen_labels:
                    continue
                seen_labels.add(key)
                results.append(
                    ExtractedTerm(
                        candidate_label=label,
                        definition=definition,
                        section=doc.section,
                        confidence=confidence,
                        metadata=doc.metadata.copy(),
                    )
                )
                break  # one match per sentence is enough

        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries while keeping multi-line glossary entries intact."""
    # Split on ". " followed by a capital letter, or on newlines
    chunks = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [c.strip() for c in chunks if c.strip()]


def _clean_label(raw: str) -> str:
    label = raw.strip().strip('""“”‘’')
    # Collapse internal whitespace
    label = re.sub(r'\s+', ' ', label)
    return label.strip()


def _clean_definition(raw: str) -> str:
    defn = raw.strip()
    # Truncate at the next sentence boundary if very long (> 60 words)
    words = defn.split()
    if len(words) > 60:
        # Find the first sentence end within reasonable bounds
        short = " ".join(words[:60])
        m = re.search(r'(?<=[.!?])\s', short)
        if m:
            defn = short[: m.start() + 1]
        else:
            defn = short + "."
    if defn and not defn[-1] in ".!?":
        defn += "."
    return defn


def _is_valid(label: str, definition: str) -> bool:
    if len(label.split()) > _MAX_LABEL_WORDS:
        return False
    if len(definition.split()) < _MIN_DEF_WORDS:
        return False
    # Reject if label contains sentence-like punctuation
    if re.search(r'[.!?,;]', label):
        return False
    # Reject sentence fragments that start with articles or demonstratives
    first_word = label.split()[0].casefold() if label else ""
    if first_word in _SENTENCE_STARTERS:
        return False
    return True
