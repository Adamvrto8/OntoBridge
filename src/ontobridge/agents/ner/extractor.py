from __future__ import annotations

import hashlib
import logging

from ontobridge.agents.harvester.protocols import ExtractedTerm, RawDocument
from ontobridge.agents.ner.backend import LLMBackend
from ontobridge.agents.ner.prompt import (
    SYSTEM_PROMPT,
    build_user_prompt,
    items_to_extracted_terms,
    parse_response,
)

logger = logging.getLogger(__name__)


class LLMNerExtractor:
    """TermExtractor that uses an LLM to identify business terms in free-form text.

    Implements the ``TermExtractor`` protocol — plug directly into
    ``HarvesterAgent(extractor=LLMNerExtractor(...))``.

    Compared to ``PatternTermExtractor``, this handles running prose (policy
    paragraphs, meeting notes, Databricks column descriptions) rather than only
    explicit "Term: Definition" glossary formats.

    Args:
        backend:              LLM backend.  Use ``OllamaBackend`` for local
                              development (zero API cost, runs offline).
        min_confidence:       Discard terms below this score (default 0.50).
        min_definition_words: Discard terms whose definition is shorter than
                              this many words (default 10, mirrors Rule 08).
    """

    def __init__(
        self,
        backend: LLMBackend,
        min_confidence: float = 0.50,
        min_definition_words: int = 10,
    ) -> None:
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError(f"min_confidence must be in [0.0, 1.0]; got {min_confidence}")
        if min_definition_words < 0:
            raise ValueError("min_definition_words must be >= 0")
        self._backend = backend
        self._min_confidence = min_confidence
        self._min_definition_words = min_definition_words
        self._cache: dict[str, list] = {}  # sha256(text) → parsed items

    def extract(self, doc: RawDocument) -> list[ExtractedTerm]:
        """Extract business terms from one RawDocument paragraph.

        Returns an empty list (never raises) when the LLM response is
        malformed — the pipeline continues with remaining documents.
        """
        if not doc.text.strip():
            return []

        key = hashlib.sha256(doc.text.encode()).hexdigest()
        if key not in self._cache:
            try:
                response = self._backend.complete(
                    system=SYSTEM_PROMPT,
                    user=build_user_prompt(doc.text),
                )
            except Exception as exc:  # noqa: BLE001 — one chunk must never abort the run
                logger.warning(
                    "LLM extraction failed for chunk (section=%s): %s",
                    doc.section, exc,
                )
                self._cache[key] = []
                return []
            self._cache[key] = parse_response(response)
        items = self._cache[key]
        terms = items_to_extracted_terms(items)

        return [
            ExtractedTerm(
                candidate_label=t.candidate_label,
                definition=t.definition,
                section=doc.section,
                confidence=t.confidence,
                metadata=doc.metadata.copy(),
            )
            for t in terms
            if t.confidence >= self._min_confidence
            and len(t.definition.split()) >= self._min_definition_words
        ]
