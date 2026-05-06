from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


def chunk_id_for(text: str, document_ref: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    h.update(b"\x00")
    h.update(document_ref.encode("utf-8"))
    return h.hexdigest()[:16]


@dataclass
class Chunk:
    chunk_id: str
    text: str
    embedding: list[float]
    document_ref: str
    section: str | None = None


@dataclass
class PolicyMatch:
    chunk_id: str
    text: str
    similarity: float   # cosine similarity, 0–1
    document_ref: str
    section: str | None = None


@runtime_checkable
class VectorStore(Protocol):
    def add_batch(self, chunks: list[Chunk]) -> None: ...
    def search(self, embedding: list[float], top_k: int) -> list[PolicyMatch]: ...
    def count(self) -> int: ...


# ---------------------------------------------------------------------------
# In-memory implementation (no extra dependencies — for tests and demos)
# ---------------------------------------------------------------------------

class InMemoryVectorStore:
    def __init__(self) -> None:
        self._chunks: list[Chunk] = []

    def add_batch(self, chunks: list[Chunk]) -> None:
        existing = {c.chunk_id for c in self._chunks}
        for chunk in chunks:
            if chunk.chunk_id not in existing:
                self._chunks.append(chunk)
                existing.add(chunk.chunk_id)

    def search(self, embedding: list[float], top_k: int) -> list[PolicyMatch]:
        if not self._chunks:
            return []
        scored = [(_cosine(embedding, c.embedding), c) for c in self._chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            PolicyMatch(
                chunk_id=c.chunk_id,
                text=c.text,
                similarity=sim,
                document_ref=c.document_ref,
                section=c.section,
            )
            for sim, c in scored[:top_k]
        ]

    def count(self) -> int:
        return len(self._chunks)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# Chroma implementation (persistent across restarts — for production)
# ---------------------------------------------------------------------------

class ChromaVectorStore:
    """VectorStore backed by ChromaDB.

    Args:
        persist_directory: Path where Chroma writes its files.  Pass ``None``
            (default) for an ephemeral in-memory client — useful in tests.
        collection_name: Chroma collection name.  One collection per linker
            instance is recommended.
    """

    def __init__(
        self,
        persist_directory: str | Path | None = None,
        collection_name: str = "policy_linker",
    ) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError(
                "chromadb is required for ChromaVectorStore.\n"
                "Install it with:  pip install chromadb\n"
                "Or:               pip install 'ontobridge[vector]'"
            ) from exc

        if persist_directory is None:
            self._client = chromadb.EphemeralClient()
        else:
            self._client = chromadb.PersistentClient(path=str(persist_directory))

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_batch(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        self._collection.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=[c.embedding for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[
                {"document_ref": c.document_ref, "section": c.section or ""}
                for c in chunks
            ],
        )

    def search(self, embedding: list[float], top_k: int) -> list[PolicyMatch]:
        total = self.count()
        if total == 0:
            return []
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, total),
        )
        matches: list[PolicyMatch] = []
        for chunk_id, text, distance, meta in zip(
            results["ids"][0],
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0],
        ):
            matches.append(
                PolicyMatch(
                    chunk_id=chunk_id,
                    text=text,
                    similarity=max(0.0, 1.0 - distance),  # cosine space: distance = 1 − similarity
                    document_ref=meta["document_ref"],
                    section=meta.get("section") or None,
                )
            )
        return matches

    def count(self) -> int:
        return self._collection.count()
