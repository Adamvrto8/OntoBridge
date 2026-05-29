from __future__ import annotations

import re

from ontobridge.agents.harvester.protocols import ExtractedTerm, RawDocument

# ---------------------------------------------------------------------------
# Definition trigger patterns for banking policy documents
# ---------------------------------------------------------------------------
# Each pattern must have exactly two named groups: (?P<term>...) and (?P<def>...)
# They are tried in order; the first match on a paragraph wins.

# Curly/smart quotes used in PDFs and Word docs (U+201C, U+201D, U+2019)
_CQ = '[“”’]'

_DEFINITION_PATTERNS: list[tuple[str, float]] = [
    # "Term" means / shall mean / is defined as / refers to DEFINITION.
    (
        _CQ + r'?(?P<term>[A-Z][A-Za-z0-9 \-/]{1,60})' + _CQ + r'?'
        r'\s+(?:means|shall mean|is defined as|refers to|is understood as|denotes)\s+'
        r'(?P<def>[A-Za-z][^\n]{20,})',
        0.90,
    ),
    # Term (ACR) means/refers to DEFINITION — "Anti-Money Laundering (AML) means ..."
    (
        r'(?P<term>[A-Z][A-Za-z0-9 \-/]{1,50})\s*\([A-Z]{2,10}\)'
        r'\s+(?:means|shall mean|is defined as|refers to|is understood as|denotes)\s+'
        r'(?P<def>[A-Za-z][^\n]{20,})',
        0.90,
    ),
    # Term (ACR): DEFINITION — "Anti-Money Laundering (AML): A regulatory framework ..."
    (
        r'(?P<term>[A-Z][A-Za-z0-9 \-/]{1,50})\s*\([A-Z]{2,10}\)\s*:\s+'
        r'(?P<def>[A-Za-z][^\n]{20,})',
        0.88,
    ),
    # TERM: DEFINITION  (glossary / catalog style)
    (
        r'^(?P<term>[A-Z][A-Za-z0-9 \-/]{1,60}):\s+(?P<def>[A-Z][^\n]{20,})',
        0.85,
    ),
    # Prose: "Term is the/a/an DEFINITION" — common in regulatory docs
    # e.g. "Identification is the first step preceding..."
    (
        r'^(?P<term>[A-Z][A-Za-z]+(?: [A-Za-z]+){0,4})'
        r' is (?:the|a|an) (?P<def>[A-Za-z][^\n]{20,})',
        0.75,
    ),
    # Prose: "Term is/are DEFINITION" without article — e.g. "Verification means checking..."
    (
        r'^(?P<term>[A-Z][A-Za-z]+(?: [A-Za-z]+){0,4})'
        r' (?:is|are) (?P<def>(?!the |a |an )[A-Za-z][^\n]{25,})',
        0.70,
    ),
    # Numbered list: "1. Term means DEFINITION" or "1. Term: DEFINITION"
    (
        r'^\s*\d+[.)]\s+(?P<term>[A-Z][A-Za-z0-9 \-/]{1,60})'
        r'(?:\s+(?:means|shall mean|refers to|is defined as|denotes|is understood as)\s+|\s*:\s+)'
        r'(?P<def>[A-Za-z][^\n]{20,})',
        0.85,
    ),
    # "TERM" - DEFINITION  (em-dash / en-dash separator)
    (
        _CQ + r'(?P<term>[A-Z][A-Za-z0-9 \-/]{1,60})' + _CQ
        + r'\s*[–—\-]\s*(?P<def>[A-Za-z][^\n]{20,})',
        0.80,
    ),
    # lowercase term (ACR), which is/means DEFINITION — "anti-money laundering (AML), which is ..."
    (
        r'(?P<term>[a-z][a-z0-9\-/ ]{3,50})\s*\([A-Z]{2,10}\)'
        r'\s*[,.]?\s*(?:which\s+(?:is|are)|means|refers to|is defined as|is\s+(?:a|an|the))\s+'
        r'(?P<def>[A-Za-z][^\n]{20,})',
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
    # prepositions / conjunctions
    "before", "after", "during", "when", "while", "if", "in",
    "on", "at", "by", "to", "for", "with", "from", "of",
}

# Minimum term character length (avoids extracting 2-char abbreviations like "KB" as terms)
_MIN_TERM_CHARS = 3


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
    """Split into matchable chunks, joining multi-line glossary entries."""
    # "What is X\nX is the..." → "X: X is the..." so the colon pattern fires
    text = re.sub(
        r'(?i)what (?:is|are) ([A-Za-z][A-Za-z ]{2,40})\s*\n+',
        lambda m: m.group(1).capitalize() + ': ',
        text,
    )
    # Join colon-terminated lines with the next line: "AML:\n  The process..." -> "AML: The process..."
    text = re.sub(r':\s*\n[ \t]*', ': ', text)
    # Join indented continuation lines: "...failure to meet\n   obligations" -> "...failure to meet obligations"
    text = re.sub(r'([a-z,])\s*\n[ \t]+', r'\1 ', text)
    # Split on sentence boundaries or remaining newlines
    chunks = re.split(r'(?<=[.!?])\s+(?=[A-Z])|\n+', text)
    return [c.strip() for c in chunks if c.strip()]


def _clean_label(raw: str) -> str:
    label = raw.strip().strip('“”’"\'')
    # Collapse internal whitespace
    label = re.sub(r'\s+', ' ', label)
    return label.strip()


def _clean_definition(raw: str) -> str:
    defn = raw.strip()
    # Strip leading list markers: "a) ", "(a) ", "1. ", "i. "
    defn = re.sub(r'^(?:[a-z]{1,3}[.)]\s+|\([a-z]\)\s+|\d+[.)]\s+)', '', defn)
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
    if len(label) < _MIN_TERM_CHARS:
        return False
    # Reject if label contains sentence-like punctuation
    if re.search(r'[.!?,;]', label):
        return False
    # Reject sentence fragments that start with articles, demonstratives, or prepositions
    first_word = label.split()[0].casefold() if label else ""
    if first_word in _SENTENCE_STARTERS:
        return False
    return True
