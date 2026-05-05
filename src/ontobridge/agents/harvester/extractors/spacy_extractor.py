from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ontobridge.agents.harvester.protocols import ExtractedTerm, RawDocument

if TYPE_CHECKING:
    import spacy

# Minimum words in a sentence to qualify as a definition
_MIN_DEF_WORDS = 8

# Noun chunk word count range that looks like a business term
_MIN_LABEL_WORDS = 2
_MAX_LABEL_WORDS = 6

# Tokens that disqualify a noun chunk from being a term label
_STOPWORD_STARTS = {
    "this", "the", "a", "an", "these", "those", "that",
    "it", "its", "they", "their", "we", "our", "all",
    "each", "some", "any", "one", "two", "three",
}

# Named-entity labels worth treating as candidate terms
_TERM_ENT_TYPES = {"ORG", "PRODUCT", "LAW", "GPE", "WORK_OF_ART", "EVENT"}


class SpaCyTermExtractor:
    """Extracts candidate (label, definition) pairs from free text using spaCy.

    Strategy
    --------
    1. Parse the document text with spaCy (tokenization + NER + noun chunks).
    2. For each sentence that is long enough to be a definition:
       a. If a named entity of a relevant type is present, use it as the label.
       b. Otherwise, look for noun chunks that have 2–6 words and start with a
          capitalised content word (not a stopword/article).
    3. Pair the found label with the full sentence text as the definition.
    4. Deduplicate by lowercased label within the document.

    This complements ``PatternTermExtractor``:  that one works best when the
    text already uses explicit glossary conventions ("X means Y").  This one
    works better on running prose and catalog descriptions where those
    conventions are absent.

    Args:
        model:       spaCy model name.  Defaults to ``en_core_web_sm``.
        confidence:  Base confidence assigned to extracted terms (0–1).
    """

    def __init__(
        self,
        model: str = "en_core_web_sm",
        confidence: float = 0.75,
    ) -> None:
        self.model_name = model
        self.confidence = confidence
        self._nlp = None

    # ------------------------------------------------------------------
    # TermExtractor interface
    # ------------------------------------------------------------------

    def extract(self, doc: RawDocument) -> list[ExtractedTerm]:
        if not doc.text or not doc.text.strip():
            return []

        nlp = self._get_nlp()
        parsed = nlp(doc.text)
        results: list[ExtractedTerm] = []
        seen_labels: set[str] = set()

        for sent in parsed.sents:
            words = sent.text.split()
            if len(words) < _MIN_DEF_WORDS:
                continue

            definition = _clean(sent.text)

            # 1. Named entities first — most reliable signal
            for ent in sent.ents:
                if ent.label_ not in _TERM_ENT_TYPES:
                    continue
                label = _clean(ent.text)
                if not _valid_label(label):
                    continue
                key = label.casefold()
                if key in seen_labels:
                    continue
                seen_labels.add(key)
                results.append(ExtractedTerm(
                    candidate_label=label,
                    definition=definition,
                    section=doc.section,
                    confidence=self.confidence + 0.10,  # boost for NER match
                    metadata=doc.metadata.copy(),
                ))

            # 2. Noun chunks as fallback
            for chunk in sent.noun_chunks:
                label = _clean(chunk.text)
                if not _valid_label(label):
                    continue
                key = label.casefold()
                if key in seen_labels:
                    continue
                seen_labels.add(key)
                results.append(ExtractedTerm(
                    candidate_label=label,
                    definition=definition,
                    section=doc.section,
                    confidence=self.confidence,
                    metadata=doc.metadata.copy(),
                ))

        return results

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _get_nlp(self) -> spacy.Language:
        if self._nlp is None:
            try:
                import spacy as _spacy
            except ImportError as exc:
                raise ImportError(
                    "spaCy is required for SpaCyTermExtractor.\n"
                    "Install it with:  pip install spacy\n"
                    "Then download the model:  python -m spacy download en_core_web_sm"
                ) from exc
            try:
                self._nlp = _spacy.load(self.model_name)
            except OSError as exc:
                raise OSError(
                    f"spaCy model {self.model_name!r} not found.\n"
                    f"Download it with:  python -m spacy download {self.model_name}"
                ) from exc
        return self._nlp

    def __repr__(self) -> str:
        return (
            f"SpaCyTermExtractor(model={self.model_name!r}, "
            f"confidence={self.confidence})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _valid_label(label: str) -> bool:
    words = label.split()
    if len(words) < _MIN_LABEL_WORDS or len(words) > _MAX_LABEL_WORDS:
        return False
    first = words[0].casefold()
    if first in _STOPWORD_STARTS:
        return False
    # Must start with a capital letter
    if not words[0][0].isupper():
        return False
    # Reject if it's all stopwords
    if all(w.casefold() in _STOPWORD_STARTS for w in words):
        return False
    return True
