from __future__ import annotations

from ontobridge.agents.mapping.glossary import GlossarySource
from ontobridge.agents.mapping.strategies import (
    DEFAULT_EMBEDDING_THRESHOLD,
    DEFAULT_FUZZY_THRESHOLD,
    EmbeddingSimilarityStrategy,
    Encoder,
    ExactMatchStrategy,
    FuzzyStringStrategy,
    Match,
)
from ontobridge.models.enrichment import EnrichedTerm
from ontobridge.models.enums import MatchType
from ontobridge.models.fibo import FIBOMatch  # noqa: F401  (re-exported convenience)
from ontobridge.models.published import PublishedTerm  # noqa: F401


MAX_ALTERNATIVES = 5


class MappingAgent:
    def __init__(
        self,
        glossary: GlossarySource,
        fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
        embedding_threshold: float = DEFAULT_EMBEDDING_THRESHOLD,
        encoder: Encoder | None = None,
    ):
        self.glossary = glossary
        self.fuzzy_threshold = fuzzy_threshold
        self.exact = ExactMatchStrategy()
        self.fuzzy = FuzzyStringStrategy(threshold=fuzzy_threshold)
        self.embedding = EmbeddingSimilarityStrategy(
            encoder=encoder,
            threshold=embedding_threshold,
        )

    def evaluate(self, term: EnrichedTerm):
        from ontobridge.models.enrichment import MatchResult

        label = term.preferred_label
        if not label:
            raise ValueError(
                "EnrichedTerm has no candidate_labels — Mapping agent needs at least one"
            )

        exact_hits = self.exact.match(label, self.glossary)
        if exact_hits:
            top = exact_hits[0]
            return MatchResult(
                match_type=MatchType.DUPLICATE,
                similarity=top.score,
                target_uri=top.target_uri,
                alternative_matches=[],
            )

        fuzzy_hits = self.fuzzy.match(label, self.glossary)
        embedding_hits = self.embedding.match(label, self.glossary)
        ranked = self._merge(fuzzy_hits, embedding_hits)

        if ranked and ranked[0].score >= self.fuzzy_threshold:
            top = ranked[0]
            return MatchResult(
                match_type=MatchType.FUZZY,
                similarity=top.score,
                target_uri=top.target_uri,
                alternative_matches=[
                    (m.target_uri, round(m.score, 4))
                    for m in ranked[1 : 1 + MAX_ALTERNATIVES]
                ],
            )

        return MatchResult(
            match_type=MatchType.NEW,
            similarity=0.0,
            alternative_matches=[
                (m.target_uri, round(m.score, 4))
                for m in ranked[:MAX_ALTERNATIVES]
            ],
        )

    def apply(self, term: EnrichedTerm) -> EnrichedTerm:
        term.match_result = self.evaluate(term)
        return term

    @staticmethod
    def _merge(fuzzy: list[Match], embedding: list[Match]) -> list[Match]:
        best_per_uri: dict[str, Match] = {}
        for m in fuzzy + embedding:
            existing = best_per_uri.get(m.target_uri)
            if existing is None or m.score > existing.score:
                best_per_uri[m.target_uri] = m
        return sorted(best_per_uri.values(), key=lambda m: m.score, reverse=True)
