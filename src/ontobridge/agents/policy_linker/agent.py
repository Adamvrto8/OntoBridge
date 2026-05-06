from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from ontobridge.agents.harvester.protocols import DocumentReader, RawDocument
from ontobridge.agents.harvester.readers.catalog import CatalogReader
from ontobridge.agents.harvester.readers.docx import DocxReader
from ontobridge.agents.harvester.readers.pdf import PdfReader
from ontobridge.agents.harvester.readers.text import PlainTextReader
from ontobridge.agents.mapping.strategies import Encoder
from ontobridge.agents.policy_linker.store import (
    Chunk,
    PolicyMatch,
    VectorStore,
    chunk_id_for,
)
from ontobridge.models.enrichment import EnrichedTerm, PolicyContext


def _default_readers() -> list[DocumentReader]:
    return [PlainTextReader(), PdfReader(), DocxReader(), CatalogReader()]


def _to_dense(mapping: Mapping[str, float]) -> list[float]:
    """Convert an index-keyed Encoder mapping to an ordered dense vector.

    SentenceTransformerEncoder returns {str(i): float} — this extracts the
    values in dimension order so they can be passed to Chroma or cosine math.
    """
    return [mapping[str(i)] for i in range(len(mapping))]


class PolicyLinkerAgent:
    """Indexes policy documents and attaches matching paragraphs to pipeline terms.

    Usage
    -----
    1. Call ``index_document()`` for each policy file.  With
       ``ChromaVectorStore(persist_directory=...)`` the index survives restarts
       and only needs to be built once per document set.
    2. Add this agent to ``PipelineRunner(policy_linker=...)`` — it calls
       ``apply(term)`` automatically before the mapping step.

    Terms without a match above *threshold* leave ``policy_context`` empty,
    which causes Governance Rule 10 to block publication until a steward
    supplies a source reference manually.

    Args:
        store:     VectorStore backend.  Use ``ChromaVectorStore`` for
                   production (disk-persistent) or ``InMemoryVectorStore``
                   for tests and ephemeral demos.
        encoder:   The same Encoder instance used by MappingAgent /
                   TaxonomyAgent — embeddings are shared so no second model
                   load occurs.
        threshold: Minimum cosine similarity to count as a valid policy match
                   (0–1, default 0.60 per CONTEXT.md specification).
        top_k:     Maximum number of policy paragraphs attached per term.
        readers:   DocumentReader list for loading policy files.  Defaults to
                   the same four readers used by HarvesterAgent.
    """

    def __init__(
        self,
        store: VectorStore,
        encoder: Encoder,
        threshold: float = 0.60,
        top_k: int = 3,
        readers: Sequence[DocumentReader] | None = None,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold must be in [0.0, 1.0]; got {threshold}")
        self._store = store
        self._encoder = encoder
        self._threshold = threshold
        self._top_k = top_k
        self._readers: list[DocumentReader] = (
            list(readers) if readers else _default_readers()
        )

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_document(
        self,
        path: Path | str,
        document_ref: str | None = None,
    ) -> int:
        """Chunk, embed, and store a policy document.

        Each ``RawDocument`` paragraph produced by the reader becomes one
        searchable chunk.  Duplicate chunks (same text + document_ref) are
        silently skipped via upsert.

        Args:
            path:         Path to the document file.
            document_ref: Human-readable identifier stored as provenance
                          (e.g. ``"CreditPolicy_v3.pdf#section-2.1"``).
                          Defaults to the file's basename.

        Returns:
            Number of chunks submitted to the store (before deduplication).
        """
        reader = self._find_reader(path)
        docs: list[RawDocument] = reader.read(path)
        doc_ref = document_ref or Path(path).name

        chunks: list[Chunk] = []
        for doc in docs:
            if not doc.text.strip():
                continue
            vec = _to_dense(self._encoder.encode(doc.text))
            chunks.append(
                Chunk(
                    chunk_id=chunk_id_for(doc.text, doc_ref),
                    text=doc.text,
                    embedding=vec,
                    document_ref=doc_ref,
                    section=doc.section,
                )
            )

        if chunks:
            self._store.add_batch(chunks)
        return len(chunks)

    # ------------------------------------------------------------------
    # Pipeline apply
    # ------------------------------------------------------------------

    def apply(self, term: EnrichedTerm) -> None:
        """Populate ``term.policy_context`` with best-matching policy paragraphs.

        Non-destructive: existing ``PolicyContext`` entries are kept; only
        new matches (by chunk_id) are appended.
        """
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
    # Raw search (debugging / evaluation)
    # ------------------------------------------------------------------

    def find(self, query: str, top_k: int | None = None) -> list[PolicyMatch]:
        """Return PolicyMatches above threshold for *query*, sorted by similarity."""
        k = top_k if top_k is not None else self._top_k
        if self._store.count() == 0:
            return []
        vec = _to_dense(self._encoder.encode(query))
        candidates = self._store.search(vec, top_k=k)
        return [m for m in candidates if m.similarity >= self._threshold]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_reader(self, source: Path | str) -> DocumentReader:
        for reader in self._readers:
            if reader.can_read(source):
                return reader
        suffix = Path(source).suffix
        raise ValueError(
            f"No reader registered for {suffix!r}. "
            f"Available: {[type(r).__name__ for r in self._readers]}"
        )
