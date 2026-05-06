from __future__ import annotations

import re

# Verbs that introduce a formal definition ("X is a ...", "X refers to ...")
_DEF_VERB = re.compile(
    r"\b(is\s+an?\b|are\s+an?\b|refers?\s+to\b|means?\b|is\s+defined\s+as\b"
    r"|represents?\b|denotes?\b|describes?\b|encompasses?\b)",
    re.IGNORECASE,
)

# Starters that signal procedural/boilerplate text — not definitions
_PROCEDURAL = re.compile(
    r"^(this|these|the\s+following|note\s+that|please|see\s+also|as\s+per"
    r"|pursuant\s+to|in\s+accordance|documentation|required\s+document"
    r"|all\s+term|section|clause|article|paragraph|schedule)",
    re.IGNORECASE,
)

# Sentence boundary: punctuation + whitespace + capital / quote / paren
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])")

_MIN_WORDS = 6
_MAX_WORDS = 60
_IDEAL_MIN = 8
_IDEAL_MAX = 35


def _split_sentences(text: str) -> list[str]:
    parts = _SENT_SPLIT.split(text.strip())
    # Also split on ": " used heavily in policy docs ("Mortgage: A loan...")
    sentences: list[str] = []
    for part in parts:
        m = re.match(r"^([^:]{1,50}):\s+(.+)$", part, re.DOTALL)
        if m and len(m.group(1).split()) <= 5:
            head, body = m.group(1).strip(), m.group(2).strip()
            if head:
                sentences.append(head)
            if body:
                sentences.append(body)
        else:
            sentences.append(part)
    return [s.strip() for s in sentences if s.strip()]


def _score(sentence: str, label: str | None) -> int:
    words = sentence.split()
    n = len(words)

    if n < _MIN_WORDS:
        return -10  # too short to be a definition

    score = 0

    if n > _MAX_WORDS:
        score -= 2
    elif _IDEAL_MIN <= n <= _IDEAL_MAX:
        score += 1

    if _PROCEDURAL.match(sentence):
        score -= 3

    lower = sentence.lower()

    if label:
        label_lower = label.lower()
        if lower.startswith(label_lower):
            rest = lower[len(label_lower):].lstrip(" ,;")
            if _DEF_VERB.match(rest):
                score += 5  # "Mortgage is a loan ..."
            else:
                score += 2
        elif label_lower in lower:
            score += 2

    if _DEF_VERB.search(lower):
        score += 2

    return score


class HeuristicDefinitionExtractor:
    """Picks the best definition sentence from a raw text passage.

    Scores each sentence using pattern heuristics — label presence,
    definition verbs, ideal length — and returns the highest-scoring one.
    Falls back to the first adequately long sentence when no sentence
    scores above zero.
    """

    def extract(self, text: str, label: str | None = None) -> str | None:
        if not text or not text.strip():
            return None

        sentences = _split_sentences(text)
        if not sentences:
            return None

        # Single sentence — return directly if long enough
        if len(sentences) == 1:
            return sentences[0] if len(sentences[0].split()) >= _MIN_WORDS else None

        scored = sorted(
            ((s, _score(s, label)) for s in sentences),
            key=lambda x: x[1],
            reverse=True,
        )

        best_sent, best_score = scored[0]
        if best_score > 0:
            return best_sent

        # No sentence scored well — fall back to first sentence of adequate length
        for s in sentences:
            if len(s.split()) >= _MIN_WORDS:
                return s

        return None
