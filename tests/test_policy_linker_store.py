from __future__ import annotations

import math
import pytest

from ontobridge.agents.policy_linker.store import (
    Chunk,
    ChromaVectorStore,
    InMemoryVectorStore,
    PolicyMatch,
    VectorStore,
    chunk_id_for,
    _cosine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unit(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


def _make_chunk(text: str, doc_ref: str, vec: list[float], section: str | None = None) -> Chunk:
    return Chunk(
        chunk_id=chunk_id_for(text, doc_ref),
        text=text,
        embedding=vec,
        document_ref=doc_ref,
        section=section,
    )


# ---------------------------------------------------------------------------
# chunk_id_for
# ---------------------------------------------------------------------------

def test_chunk_id_deterministic():
    assert chunk_id_for("hello", "doc.pdf") == chunk_id_for("hello", "doc.pdf")


def test_chunk_id_differs_by_text():
    assert chunk_id_for("hello", "doc.pdf") != chunk_id_for("world", "doc.pdf")


def test_chunk_id_differs_by_ref():
    assert chunk_id_for("hello", "a.pdf") != chunk_id_for("hello", "b.pdf")


def test_chunk_id_length():
    assert len(chunk_id_for("x", "y")) == 16


# ---------------------------------------------------------------------------
# _cosine
# ---------------------------------------------------------------------------

def test_cosine_identical_vectors():
    v = _unit([1.0, 0.0, 0.0])
    assert abs(_cosine(v, v) - 1.0) < 1e-9


def test_cosine_orthogonal():
    a = _unit([1.0, 0.0])
    b = _unit([0.0, 1.0])
    assert abs(_cosine(a, b)) < 1e-9


def test_cosine_zero_vector():
    assert _cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# InMemoryVectorStore
# ---------------------------------------------------------------------------

class TestInMemoryVectorStore:
    def test_empty_count(self):
        store = InMemoryVectorStore()
        assert store.count() == 0

    def test_add_and_count(self):
        store = InMemoryVectorStore()
        store.add_batch([_make_chunk("text", "doc.pdf", _unit([1.0, 0.0]))])
        assert store.count() == 1

    def test_deduplication(self):
        store = InMemoryVectorStore()
        chunk = _make_chunk("text", "doc.pdf", _unit([1.0, 0.0]))
        store.add_batch([chunk, chunk])
        assert store.count() == 1

    def test_add_twice_same_id(self):
        store = InMemoryVectorStore()
        chunk = _make_chunk("text", "doc.pdf", _unit([1.0, 0.0]))
        store.add_batch([chunk])
        store.add_batch([chunk])
        assert store.count() == 1

    def test_search_empty(self):
        store = InMemoryVectorStore()
        assert store.search(_unit([1.0, 0.0]), top_k=3) == []

    def test_search_returns_sorted_by_similarity(self):
        store = InMemoryVectorStore()
        high = _make_chunk("high", "doc.pdf", _unit([1.0, 0.0]))
        low = _make_chunk("low", "doc.pdf", _unit([0.1, 0.99]))
        store.add_batch([low, high])
        query = _unit([1.0, 0.0])
        results = store.search(query, top_k=2)
        assert results[0].text == "high"
        assert results[0].similarity > results[1].similarity

    def test_search_top_k_limits_results(self):
        store = InMemoryVectorStore()
        for i in range(5):
            store.add_batch([_make_chunk(f"text {i}", "doc.pdf", _unit([float(i + 1), 0.0]))])
        results = store.search(_unit([1.0, 0.0]), top_k=2)
        assert len(results) <= 2

    def test_search_similarity_range(self):
        store = InMemoryVectorStore()
        store.add_batch([_make_chunk("text", "doc.pdf", _unit([1.0, 0.0]))])
        results = store.search(_unit([1.0, 0.0]), top_k=1)
        assert 0.0 <= results[0].similarity <= 1.0

    def test_search_preserves_metadata(self):
        store = InMemoryVectorStore()
        chunk = Chunk(
            chunk_id="abc123",
            text="policy paragraph",
            embedding=_unit([1.0, 0.0]),
            document_ref="PolicyDoc.pdf",
            section="§2.1",
        )
        store.add_batch([chunk])
        result = store.search(_unit([1.0, 0.0]), top_k=1)[0]
        assert result.document_ref == "PolicyDoc.pdf"
        assert result.section == "§2.1"
        assert result.chunk_id == "abc123"

    def test_satisfies_protocol(self):
        assert isinstance(InMemoryVectorStore(), VectorStore)


# ---------------------------------------------------------------------------
# ChromaVectorStore (skipped if chromadb not installed)
# ---------------------------------------------------------------------------

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")
import uuid


class TestChromaVectorStore:
    def _store(self) -> ChromaVectorStore:
        # unique collection name per test — chromadb v1.x shares state
        # across EphemeralClient instances within the same process
        return ChromaVectorStore(persist_directory=None, collection_name=f"test_{uuid.uuid4().hex}")

    def test_empty_count(self):
        assert self._store().count() == 0

    def test_add_and_count(self):
        store = self._store()
        store.add_batch([_make_chunk("text", "doc.pdf", _unit([1.0, 0.0, 0.0]))])
        assert store.count() == 1

    def test_upsert_is_idempotent(self):
        store = self._store()
        chunk = _make_chunk("text", "doc.pdf", _unit([1.0, 0.0, 0.0]))
        store.add_batch([chunk])
        store.add_batch([chunk])
        assert store.count() == 1

    def test_search_empty(self):
        store = self._store()
        assert store.search(_unit([1.0, 0.0, 0.0]), top_k=3) == []

    def test_search_returns_match(self):
        store = self._store()
        store.add_batch([_make_chunk("credit policy", "doc.pdf", _unit([1.0, 0.0, 0.0]))])
        results = store.search(_unit([1.0, 0.0, 0.0]), top_k=1)
        assert len(results) == 1
        assert results[0].text == "credit policy"

    def test_search_similarity_bounded(self):
        store = self._store()
        store.add_batch([_make_chunk("text", "doc.pdf", _unit([1.0, 0.0, 0.0]))])
        results = store.search(_unit([1.0, 0.0, 0.0]), top_k=1)
        assert 0.0 <= results[0].similarity <= 1.0

    def test_search_preserves_section(self):
        store = self._store()
        chunk = Chunk(
            chunk_id="xyz999",
            text="some paragraph",
            embedding=_unit([1.0, 0.0, 0.0]),
            document_ref="Policy.pdf",
            section="§3",
        )
        store.add_batch([chunk])
        result = store.search(_unit([1.0, 0.0, 0.0]), top_k=1)[0]
        assert result.section == "§3"
        assert result.document_ref == "Policy.pdf"

    def test_top_k_capped_at_count(self):
        store = self._store()
        store.add_batch([_make_chunk("only one", "doc.pdf", _unit([1.0, 0.0, 0.0]))])
        results = store.search(_unit([1.0, 0.0, 0.0]), top_k=10)
        assert len(results) == 1
