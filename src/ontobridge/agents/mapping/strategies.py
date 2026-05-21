from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import ClassVar, Mapping, Protocol, runtime_checkable

from ontobridge.agents.mapping.glossary import GlossaryEntry, GlossarySource

DEFAULT_FUZZY_THRESHOLD = 0.75
DEFAULT_EMBEDDING_THRESHOLD = 0.50

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Match:
    target_uri: str
    label: str
    label_kind: str  # "prefLabel" | "altLabel"
    score: float
    strategy: str


def _iter_labels(entry: GlossaryEntry) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = [(entry.pref_label, "prefLabel")]
    out.extend((alt, "altLabel") for alt in entry.alt_labels)
    return out


class MatchingStrategy(ABC):
    name: ClassVar[str]

    @abstractmethod
    def match(self, query: str, glossary: GlossarySource) -> list[Match]:
        ...


# ----------------- Strategy 1: Exact -----------------

class ExactMatchStrategy(MatchingStrategy):
    name = "exact"

    def match(self, query: str, glossary: GlossarySource) -> list[Match]:
        target = query.casefold()
        for entry in glossary.entries():
            for label, kind in _iter_labels(entry):
                if label.casefold() == target:
                    return [
                        Match(
                            target_uri=entry.uri,
                            label=label,
                            label_kind=kind,
                            score=1.0,
                            strategy=self.name,
                        )
                    ]
        return []


# ----------------- Strategy 2: Fuzzy string distance -----------------

class FuzzyStringStrategy(MatchingStrategy):
    name = "fuzzy"

    def __init__(self, threshold: float = DEFAULT_FUZZY_THRESHOLD):
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be in [0.0, 1.0]")
        self.threshold = threshold

    def match(self, query: str, glossary: GlossarySource) -> list[Match]:
        q = query.casefold()
        results: list[Match] = []
        for entry in glossary.entries():
            best_for_entry: Match | None = None
            for label, kind in _iter_labels(entry):
                score = SequenceMatcher(None, q, label.casefold()).ratio()
                if score < self.threshold or score >= 1.0:
                    continue
                if best_for_entry is None or score > best_for_entry.score:
                    best_for_entry = Match(
                        target_uri=entry.uri,
                        label=label,
                        label_kind=kind,
                        score=score,
                        strategy=self.name,
                    )
            if best_for_entry is not None:
                results.append(best_for_entry)
        results.sort(key=lambda m: m.score, reverse=True)
        return results


# ----------------- Strategy 3: Embedding cosine (token overlap fallback) -----------------

@runtime_checkable
class Encoder(Protocol):
    def encode(self, text: str) -> Mapping[str, float]: ...


class TokenOverlapEncoder:
    """Sparse term-frequency encoder. Stand-in for a real embedding model."""

    def encode(self, text: str) -> Mapping[str, float]:
        tokens = _TOKEN_RE.findall(text.casefold())
        return Counter(tokens)


class TFIDFEncoder:
    """TF-IDF encoder built from a corpus of ontology concept labels.

    Weights tokens by how distinctive they are across the ontology corpus.
    Common tokens like 'the', 'a', 'of' get low IDF; rare banking-specific
    tokens like 'collateral', 'delinquency' get high IDF.

    Unknown tokens (not seen in corpus) receive the maximum IDF weight —
    they are assumed to be highly specific and distinctive.

    Use ``TFIDFEncoder.from_ontology(ontology)`` to build from an OntologyIndex.
    """

    def __init__(self, corpus: list[str]) -> None:
        N = len(corpus) or 1
        df: Counter = Counter()
        for doc in corpus:
            tokens = set(_TOKEN_RE.findall(doc.casefold()))
            df.update(tokens)
        # Smoothed IDF: log((N+1)/(df+1)) + 1  (same formula as sklearn)
        self._idf: dict[str, float] = {
            token: math.log((N + 1) / (count + 1)) + 1.0
            for token, count in df.items()
        }
        self._default_idf = math.log(N + 1) + 1.0  # unseen tokens

    @classmethod
    def from_ontology(cls, ontology) -> "TFIDFEncoder":
        """Build a TFIDFEncoder from all concept labels, alt labels and definitions."""
        docs: list[str] = []
        for concept in ontology.concepts:
            docs.append(concept.pref_label)
            docs.extend(concept.alt_labels)
            if concept.definition:
                docs.append(concept.definition)
        return cls(docs)

    def encode(self, text: str) -> Mapping[str, float]:
        tokens = _TOKEN_RE.findall(text.casefold())
        if not tokens:
            return {}
        tf = Counter(tokens)
        n = len(tokens)
        return {
            token: (count / n) * self._idf.get(token, self._default_idf)
            for token, count in tf.items()
        }


def _cosine(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b.get(k, 0.0) for k in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class EmbeddingSimilarityStrategy(MatchingStrategy):
    name = "embedding"

    def __init__(
        self,
        encoder: Encoder | None = None,
        threshold: float = DEFAULT_EMBEDDING_THRESHOLD,
    ):
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be in [0.0, 1.0]")
        self.encoder: Encoder = encoder if encoder is not None else TokenOverlapEncoder()
        self.threshold = threshold

    def match(self, query: str, glossary: GlossarySource) -> list[Match]:
        q_vec = self.encoder.encode(query)
        results: list[Match] = []
        for entry in glossary.entries():
            best_for_entry: Match | None = None
            for label, kind in _iter_labels(entry):
                e_vec = self.encoder.encode(label)
                score = _cosine(q_vec, e_vec)
                if score < self.threshold or score >= 1.0:
                    continue
                if best_for_entry is None or score > best_for_entry.score:
                    best_for_entry = Match(
                        target_uri=entry.uri,
                        label=label,
                        label_kind=kind,
                        score=score,
                        strategy=self.name,
                    )
            if best_for_entry is not None:
                results.append(best_for_entry)
        results.sort(key=lambda m: m.score, reverse=True)
        return results
