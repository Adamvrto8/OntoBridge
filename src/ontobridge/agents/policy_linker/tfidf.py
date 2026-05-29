"""TF-IDF policy linker — no extra dependencies.

Drop-in replacement for PolicyLinkerAgent when chromadb is not available.
Uses sparse TF cosine similarity to match term label+definition against
indexed document paragraphs.

Threshold is set lower than the chromadb version (0.30 vs 0.60) because
sparse bag-of-words similarity is inherently lower than dense embeddings.
0.30 requires meaningful token overlap without being as strict as dense
embedding similarity.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Sequence

from ontobridge.agents.policy_linker.store import PolicyMatch, chunk_id_for
from ontobridge.models.enrichment import EnrichedTerm, PolicyContext


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_PARA_SPLIT = re.compile(r"\n{2,}|\r\n{2,}")
_MIN_PARA_WORDS = 5


def _tokenize(text: str) -> Counter:
    return Counter(_TOKEN_RE.findall(text.casefold()))


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b.get(k, 0) for k in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class _StoredParagraph:
    __slots__ = ("chunk_id", "text", "tokens", "document_ref", "section")

    def __init__(
        self,
        chunk_id: str,
        text: str,
        tokens: Counter,
        document_ref: str,
        section: str | None,
    ) -> None:
        self.chunk_id = chunk_id
        self.text = text
        self.tokens = tokens
        self.document_ref = document_ref
        self.section = section


class TFIDFPolicyLinker:
    """Policy linker using TF cosine similarity — no chromadb required.

    Usage mirrors PolicyLinkerAgent:
    1. Call ``index_document()`` for each policy file before running the pipeline.
    2. Pass the linker to ``BatchPipelineRunner(policy_linker=...)``.

    Args:
        threshold: Minimum cosine similarity to count as a valid match (0-1).
                   Default 0.30 — lower than the chromadb version (0.60)
                   because sparse similarity scores are inherently lower.
        top_k:     Maximum policy paragraphs attached per term.
    """

    def __init__(self, threshold: float = 0.30, top_k: int = 3) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold must be in [0.0, 1.0]; got {threshold}")
        self._threshold = threshold
        self._top_k = top_k
        self._paragraphs: list[_StoredParagraph] = []
        self._seen_ids: set[str] = set()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_text(
        self,
        text: str,
        document_ref: str,
        section: str | None = None,
    ) -> int:
        """Index paragraphs from a raw text string.

        Returns the number of paragraphs indexed (after deduplication).
        """
        chunks = self._chunk(text, document_ref, section)
        added = 0
        for para in chunks:
            if para.chunk_id not in self._seen_ids:
                self._paragraphs.append(para)
                self._seen_ids.add(para.chunk_id)
                added += 1
        return added

    def index_document(
        self,
        path: Path | str,
        document_ref: str | None = None,
    ) -> int:
        """Read and index a policy document (txt, pdf, docx).

        Returns the number of paragraphs indexed.
        """
        from ontobridge.agents.harvester.readers.catalog import CatalogReader
        from ontobridge.agents.harvester.readers.docx import DocxReader
        from ontobridge.agents.harvester.readers.pdf import PdfReader
        from ontobridge.agents.harvester.readers.text import PlainTextReader

        path = Path(path)
        doc_ref = document_ref or path.name
        suffix = path.suffix.lower()

        readers = [PlainTextReader(), PdfReader(), DocxReader(), CatalogReader()]
        reader = next((r for r in readers if r.can_read(path)), None)
        if reader is None:
            raise ValueError(f"No reader for {suffix!r}")

        docs = reader.read(path)
        added = 0
        for doc in docs:
            if doc.text.strip():
                added += self.index_text(doc.text, doc_ref, section=doc.section)
        return added

    # ------------------------------------------------------------------
    # Pipeline apply (same interface as PolicyLinkerAgent)
    # ------------------------------------------------------------------

    def apply(self, term: EnrichedTerm) -> None:
        """Populate ``term.policy_context`` with best-matching paragraphs."""
        label = term.preferred_label or ""
        definition = term.definition or ""
        query = f"{label} {definition}".strip()
        if not query:
            return

        matches = self.find(query)
        existing_ids = {pc.chunk_id for pc in term.policy_context if pc.chunk_id}
        for match in matches:
            if match.chunk_id not in existing_ids:
                term.policy_context.append(
                    PolicyContext(
                        paragraph=match.text,
                        document_ref=match.document_ref,
                        section=match.section,
                        chunk_id=match.chunk_id,
                        similarity=match.similarity,
                    )
                )
                existing_ids.add(match.chunk_id)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def find(self, query: str, top_k: int | None = None) -> list[PolicyMatch]:
        """Return paragraphs above threshold sorted by similarity."""
        if not self._paragraphs:
            return []
        k = top_k if top_k is not None else self._top_k
        q_tokens = _tokenize(query)
        scored = [
            (_cosine(q_tokens, p.tokens), p)
            for p in self._paragraphs
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            PolicyMatch(
                chunk_id=p.chunk_id,
                text=p.text,
                similarity=sim,
                document_ref=p.document_ref,
                section=p.section,
            )
            for sim, p in scored[:k]
            if sim >= self._threshold
        ]

    def count(self) -> int:
        return len(self._paragraphs)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _chunk(
        self,
        text: str,
        document_ref: str,
        section: str | None,
    ) -> list[_StoredParagraph]:
        raw_paras = _PARA_SPLIT.split(text.strip())
        result: list[_StoredParagraph] = []
        for para in raw_paras:
            para = para.strip()
            if not para or len(para.split()) < _MIN_PARA_WORDS:
                continue
            tokens = _tokenize(para)
            if not tokens:
                continue
            result.append(_StoredParagraph(
                chunk_id=chunk_id_for(para, document_ref),
                text=para,
                tokens=tokens,
                document_ref=document_ref,
                section=section,
            ))
        return result
