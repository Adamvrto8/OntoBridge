from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
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

_DEFAULT_OVERRIDES = (
    Path(__file__).resolve().parents[4] / "ontology" / "taxonomy_overrides.json"
)

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
        overrides_path: Path | str | None = _DEFAULT_OVERRIDES,
        llm_backend=None,
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
        self._overrides: dict[str, str] = self._load_overrides(overrides_path)
        # Optional LLM used to classify the scheme directly by meaning, instead
        # of inheriting it from a lexically-matched broader concept.
        self.llm_backend = llm_backend
        self._scheme_cache: dict[str, str] = {}
        self._scheme_system_prompt: str | None = None

    @staticmethod
    def _load_overrides(path: Path | str | None) -> dict[str, str]:
        if path is None:
            return {}
        p = Path(path)
        if not p.exists():
            return {}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return {
                k.casefold(): v
                for k, v in data.items()
                if not k.startswith("_") and isinstance(v, str)
            }
        except Exception:
            return {}

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
            # When token overlap gives nothing, pick the closest scheme by fuzzy name match
            scheme_uri = (top.concept.scheme if top else None) or self._fallback_scheme(label)
            return TaxonomyPlacement(
                broader_concept_uri=top.concept.uri if top else None,
                scheme_uri=scheme_uri,
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

    def apply(self, term: EnrichedTerm, classify_scheme: bool = True) -> EnrichedTerm:
        # 1. Manual overrides — highest priority
        override = self._overrides.get((term.preferred_label or "").casefold())
        if override:
            concept = self.ontology.by_uri(override)
            term.taxonomy_placement = TaxonomyPlacement(
                broader_concept_uri=override,
                scheme_uri=concept.scheme if concept else None,
                domain_prefix=build_curie(term.preferred_label or "", self.curie_prefix),
                placement_confidence=1.0,
                status=PlacementStatus.PLACED,
                sibling_conflicts=[],
            )
            return term

        # 2. FIBO hierarchy — when matcher found a broader concept
        fibo = term.fibo_match
        if fibo and fibo.broader_uri:
            term.taxonomy_placement = self._fibo_placement(term, fibo)
        else:
            # 3. Similarity algorithm with length penalty
            term.taxonomy_placement = self.evaluate(term)

        # 4. Scheme — classify by meaning rather than inheriting it from the
        #    broader concept, which is often a lexical false-friend (e.g.
        #    "Foundation Fund" placed under "SourceOfFunds"). No-op without an LLM.
        #    The pipeline defers this (classify_scheme=False) until the definition
        #    agent has polished term.definition, then calls apply_scheme().
        if classify_scheme:
            self._apply_llm_scheme(term)
            self._reconcile_broader_with_scheme(term)
        return term

    def apply_scheme(self, term: EnrichedTerm) -> None:
        """Classify the scheme from the (now-final) definition.

        Call after the definition agent has rewritten ``term.definition`` — a
        complete definition classifies far better than the raw harvested
        snippet. Respects manual overrides and is a no-op without an LLM.
        """
        if self._overrides.get((term.preferred_label or "").casefold()):
            return  # explicit override — keep its scheme
        self._apply_llm_scheme(term)
        self._reconcile_broader_with_scheme(term)

    def _apply_llm_scheme(self, term: EnrichedTerm) -> None:
        placement = term.taxonomy_placement
        if placement is None:
            return
        scheme_uri = self._classify_scheme(term)
        if scheme_uri:
            placement.scheme_uri = scheme_uri

    def _reconcile_broader_with_scheme(self, term: EnrichedTerm) -> None:
        """Keep the broader concept consistent with the classified scheme.

        Scheme classification is decoupled from broader-concept placement, so a
        term can end up with an LLM scheme (e.g. Process) while its nearest-
        neighbour parent sits in another scheme (e.g. an Organisation role like
        "Relationship manager"). When that happens, re-pick the best parent
        *within the classified scheme*; if none clears the threshold, mark the
        placement UNRESOLVED rather than assert a cross-scheme parent.

        FIBO-anchored parents (not present in the local ontology) are left
        untouched — their hierarchy is intentional.
        """
        placement = term.taxonomy_placement
        if placement is None or not placement.scheme_uri:
            return
        broader_uri = placement.broader_concept_uri
        parent = self.ontology.by_uri(broader_uri) if broader_uri else None
        if broader_uri and parent is None:
            return  # FIBO / external parent — leave it
        if parent is not None and parent.scheme == placement.scheme_uri:
            return  # already consistent

        label = term.preferred_label or ""
        best = self._best_parent_in_scheme(
            label, placement.scheme_uri, self._excluded_uri(term)
        )
        if best is not None and best.score >= self.placement_threshold:
            placement.broader_concept_uri = best.concept.uri
            placement.placement_confidence = best.score
            placement.status = PlacementStatus.PLACED
            placement.sibling_conflicts = self._sibling_conflicts(label, best.concept.uri)
        else:
            placement.broader_concept_uri = None
            placement.placement_confidence = best.score if best is not None else 0.0
            placement.status = PlacementStatus.UNRESOLVED
            placement.sibling_conflicts = []

    def _best_parent_in_scheme(
        self, label: str, scheme_uri: str, excluded_uri: str | None
    ) -> _ParentScore | None:
        """Highest-scoring candidate parent that belongs to ``scheme_uri``."""
        for p in self._rank_parents(label, excluded_uri):
            if p.concept.scheme == scheme_uri:
                return p
        return None

    def _classify_scheme(self, term: EnrichedTerm) -> str | None:
        if self.llm_backend is None:
            return None
        label = (term.preferred_label or "").strip()
        if not label:
            return None
        key = label.casefold()
        if key in self._scheme_cache:
            return self._scheme_cache[key]

        catalog = self.ontology.scheme_catalog()
        if not catalog:
            return None
        if self._scheme_system_prompt is None:
            self._scheme_system_prompt = self._build_scheme_prompt(catalog)

        definition = (term.definition or "").strip()
        user = f"Term: {label}"
        if definition:
            user += f"\nDefinition: {definition[:600]}"

        try:
            response = self.llm_backend.complete(
                system=self._scheme_system_prompt, user=user
            )
        except Exception:  # noqa: BLE001 — scheme classification must never abort the run
            return None

        scheme_uri = self._match_scheme(response, catalog)
        if scheme_uri is not None:
            self._scheme_cache[key] = scheme_uri
        return scheme_uri

    @staticmethod
    def _build_scheme_prompt(catalog: list[tuple[str, str, str]]) -> str:
        lines = [
            "You are an ontology classifier for a retail bank's business glossary.",
            "Classify the term into EXACTLY ONE concept scheme from the list below.",
            "",
            "Classify by what the term fundamentally IS — its intrinsic type — NOT",
            "by the regulatory or business context it is discussed in. A cash",
            "transaction is a Process even when described in an anti-money-laundering",
            "rule; a beneficial owner is a Party even when discussed for compliance;",
            "an identity document is a Document. Pick the structural scheme that",
            "matches the term's nature (a person/role → Party, a thing owned/sold →",
            "Product, an activity/procedure → Process, a record/form → Document).",
            "",
            "Use the Compliance / Regulatory scheme ONLY for actual regulations,",
            "legal obligations, compliance controls, and regulatory frameworks",
            "themselves — never as a catch-all for ordinary terms that merely appear",
            "in a compliance document.",
            "",
            "Reply with ONLY the scheme label, copied verbatim — no other text.",
            "",
            "Concept schemes:",
        ]
        for _uri, scheme_label, desc in catalog:
            lines.append(f"- {scheme_label}: {desc}" if desc else f"- {scheme_label}")
        return "\n".join(lines)

    @staticmethod
    def _match_scheme(
        response: str, catalog: list[tuple[str, str, str]]
    ) -> str | None:
        text = (response or "").strip().casefold()
        if not text:
            return None
        # Exact label match first.
        for uri, scheme_label, _ in catalog:
            if text == scheme_label.casefold():
                return uri
        # Then containment either way — handles the model echoing "Party" for
        # "Party / Customer" or wrapping the label in a short sentence.
        for uri, scheme_label, _ in catalog:
            lc = scheme_label.casefold()
            if lc in text or text in lc:
                return uri
        return None

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
        query_tokens = set(label_cf.split())
        scored: list[_ParentScore] = []
        for c in self.ontology.concepts:
            if excluded_uri is not None and c.uri == excluded_uri:
                continue
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
                # Penalise candidates that are more specific than the query:
                # if query tokens are a subset of the candidate's tokens the
                # candidate is likely a child/sibling, not a parent.
                cand_tokens = set(best_label.casefold().split())
                if query_tokens and query_tokens.issubset(cand_tokens) and len(cand_tokens) > len(query_tokens):
                    best_score *= 0.25
                else:
                    # Mild length penalty — shorter labels tend to be more general
                    extra_words = max(0, len(cand_tokens) - 2)
                    best_score /= 1.0 + 0.2 * extra_words
                scored.append(_ParentScore(concept=c, score=best_score, matched_label=best_label))
        scored.sort(key=lambda p: (-p.score, p.concept.uri))
        return scored

    def _fallback_scheme(self, label: str) -> str | None:
        """Pick the best scheme by fuzzy label match when token overlap gives nothing."""
        best_uri: str | None = None
        best_score = 0.0
        for scheme_uri, scheme_label in self.ontology._scheme_labels.items():
            score = SequenceMatcher(None, label.casefold(), scheme_label.casefold()).ratio()
            if score > best_score:
                best_score = score
                best_uri = scheme_uri
        return best_uri

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
