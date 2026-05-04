from __future__ import annotations

from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer as _ST


class SentenceTransformerEncoder:
    """Dense encoder backed by a sentence-transformers model.

    Satisfies the ``Encoder`` protocol used by ``MappingAgent`` and
    ``TaxonomyAgent``.  Returns embeddings as ``dict[str, float]`` keyed by
    dimension index so the existing ``_cosine`` sparse-dot-product function
    works without modification (both vectors share identical key sets).

    The underlying model is loaded lazily on the first ``encode`` call so
    importing this class never blocks — useful in Streamlit where the module
    is imported at startup long before any term is processed.

    Encoded texts are cached per-instance (unbounded) to avoid re-encoding
    the same ontology label dozens of times across a single pipeline run.

    Args:
        model_name: Any model name accepted by ``sentence-transformers``.
            Defaults to ``all-MiniLM-L6-v2`` — 80 MB, 384 dimensions, fast.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: _ST | None = None
        self._cache: dict[str, dict[str, float]] = {}

    # ------------------------------------------------------------------
    # Encoder protocol
    # ------------------------------------------------------------------

    def encode(self, text: str) -> Mapping[str, float]:
        if text not in self._cache:
            self._cache[text] = self._embed(text)
        return self._cache[text]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_model(self) -> _ST:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImportError(
                    "sentence-transformers is required for SentenceTransformerEncoder.\n"
                    "Install it with:  pip install sentence-transformers"
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _embed(self, text: str) -> dict[str, float]:
        model = self._get_model()
        vector = model.encode(text, normalize_embeddings=True)
        return {str(i): float(v) for i, v in enumerate(vector)}

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def clear_cache(self) -> None:
        """Drop all cached embeddings (useful in tests or after model swap)."""
        self._cache.clear()

    def __repr__(self) -> str:
        cached = len(self._cache)
        loaded = self._model is not None
        return (
            f"SentenceTransformerEncoder(model={self.model_name!r}, "
            f"loaded={loaded}, cached_texts={cached})"
        )
