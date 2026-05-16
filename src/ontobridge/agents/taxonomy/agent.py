from __future__ import annotations

import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Mapping

from ontobridge.agents.governance.ontology import ConceptRecord, OntologyIndex
from ontobridge.agents.mapping.strategies import Encoder, TokenOverlapEncoder
from ontobridge.models.enrichment import (
    EnrichedTerm,
    SiblingConflict,
    TaxonomyPlacement,
)
from ontobridge.models.enums import MatchType, PlacementStatus

DEFAULT_PLACEMENT_THRESHOLD = 0.5
DEFAULT_SIBLING_CONFLICT_THRESHOLD = 0.80
DEFAULT_CURIE_PREFIX = "bank"

_TOKEN_SPLIT = re.compile(r"[\s\-_./]+")


def camelcase_label(label: str) -> str:
    parts = [p for p in _TOKEN_SPLIT.split(label.strip()) if p]
    out: list[str] = []
    for p in parts:
        if p.isupper():
            out.append(p)
        else:
            out.append(p[:1].upper() + p[1:])
    return "".join(out)


def build_curie(label: str, prefix: str = DEFAULT_CURIE_PREFIX) -> str:
    suffix = camelcase_label(label)
    if not suffix:
        return ""
    return f"{prefix}:{suffix}"


def _cosine(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b.get(k, 0.0) for k in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    raw = dot / (na * nb)
    if raw < 0.0:
        return 0.0
    if raw > 1.0:
        return 1.0
    return raw


@dataclass(frozen=True)
class _ParentScore:
    concept: ConceptRecord
    score: float
    matched_label: str


class TaxonomyAgent:
    def __init__(
        self,
        ontology: OntologyIndex,
        encoder: Encoder | None = None,
        placement_threshold: float = DEFAULT_PLACEMENT_THRESHOLD,
        sibling_conflict_threshold: float = DEFAULT_SIBLING_CONFLICT_THRESHOLD,
        curie_prefix: str = DEFAULT_CURIE_PREFIX,
    ):
        if not 0.0 <= placement_threshold <= 1.0:
            raise ValueError("placement_threshold must be in [0.0, 1.0]")
        if not 0.0 <= sibling_conflict_threshold <= 1.0:
            raise ValueError("sibling_conflict_threshold must be in [0.0, 1.0]")
        self.ontology = ontology
        self.encoder: Encoder = encoder if encoder is not None else TokenOverlapEncoder()
        self.placement_threshold = placement_threshold
        self.sibling_conflict_threshold = sibling_conflict_threshold
        self.curie_prefix = curie_prefix

    def evaluate(self, term: EnrichedTerm) -> TaxonomyPlacement:
        label = term.preferred_label
        if not label:
            raise ValueError(
                "EnrichedTerm has no candidate_labels — Taxonomy agent needs at least one"
            )

        excluded_uri = self._excluded_uri(term)
        ranked = self._rank_parents(label, excluded_uri)

        if not ranked or ranked[0].score < self.placement_threshold:
            top = ranked[0] if ranked else None
            return TaxonomyPlacement(
                broader_concept_uri=top.concept.uri if top else None,
                scheme_uri=top.concept.scheme if top else None,
                domain_prefix=build_curie(label, self.curie_prefix),
                placement_confidence=top.score if top else 0.0,
                status=PlacementStatus.UNRESOLVED,
                sibling_conflicts=[],
            )

        top = ranked[0]
        siblings = self._sibling_conflicts(label, top.concept.uri)
        return TaxonomyPlacement(
            broader_concept_uri=top.concept.uri,
            scheme_uri=top.concept.scheme,
            domain_prefix=build_curie(label, self.curie_prefix),
            placement_confidence=top.score,
            status=PlacementStatus.PLACED,
            sibling_conflicts=siblings,
        )

    def apply(self, term: EnrichedTerm) -> EnrichedTerm:
        fibo = term.fibo_match
        if fibo and fibo.broader_uri:
            term.taxonomy_placement = self._fibo_placement(term, fibo)
        else:
            term.taxonomy_placement = self.evaluate(term)
        return term

    def _fibo_placement(self, term: EnrichedTerm, fibo) -> TaxonomyPlacement:
        scheme_uri = (
            f"https://spec.edmcouncil.org/fibo/ontology/{fibo.module}/"
            if fibo.module
            else fibo.broader_uri
        )
        return TaxonomyPlacement(
            broader_concept_uri=fibo.broader_uri,
            scheme_uri=scheme_uri,
            domain_prefix=build_curie(term.preferred_label or "", self.curie_prefix),
            placement_confidence=0.95,
            status=PlacementStatus.PLACED,
            sibling_conflicts=[],
        )

    @staticmethod
    def _excluded_uri(term: EnrichedTerm) -> str | None:
        if term.match_result is None:
            return None
        if term.match_result.match_type in {MatchType.DUPLICATE, MatchType.FUZZY}:
            return term.match_result.target_uri
        return None

    def _rank_parents(self, label: str, excluded_uri: str | None) -> list[_ParentScore]:
        q_vec = self.encoder.encode(label)
        label_cf = label.casefold()
        scored: list[_ParentScore] = []
        for c in self.ontology.concepts:
            if excluded_uri is not None and c.uri == excluded_uri:
                continue
            # A concept cannot be its own broader concept
            if c.pref_label.casefold() == label_cf:
                continue
            best_score = 0.0
            best_label = c.pref_label
            for cand_label in (c.pref_label, *c.alt_labels):
                score = _cosine(q_vec, self.encoder.encode(cand_label))
                if score > best_score:
                    best_score = score
                    best_label = cand_label
            if best_score > 0.0:
                scored.append(_ParentScore(concept=c, score=best_score, matched_label=best_label))
        scored.sort(key=lambda p: (-p.score, p.concept.uri))
        return scored

    def _sibling_conflicts(self, label: str, parent_uri: str) -> list[SiblingConflict]:
        q = label.casefold()
        conflicts: list[SiblingConflict] = []
        for sibling_uri in self.ontology.get_narrower(parent_uri):
            sibling = self.ontology.by_uri(sibling_uri)
            if sibling is None:
                continue
            best: tuple[str, float] | None = None
            for sib_label in (sibling.pref_label, *sibling.alt_labels):
                sim = SequenceMatcher(None, q, sib_label.casefold()).ratio()
                if sim >= self.sibling_conflict_threshold and (
                    best is None or sim > best[1]
                ):
                    best = (sib_label, sim)
            if best is not None:
                conflicts.append(
                    SiblingConflict(
                        sibling_uri=sibling_uri,
                        sibling_label=best[0],
                        similarity=best[1],
                    )
                )
        conflicts.sort(key=lambda c: c.similarity, reverse=True)
        return conflicts
