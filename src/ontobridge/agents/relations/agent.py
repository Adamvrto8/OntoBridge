from __future__ import annotations

from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.agents.relations.extractor import (
    RegexHeuristicExtractor,
    SVOExtractor,
    SVOTriple,
)
from ontobridge.agents.relations.lexicon import InverseVerbLexicon
from ontobridge.models.enrichment import EnrichedTerm, SemanticRelation
from ontobridge.models.enums import RelationStatus

UNRESOLVED_VERB_CONFIDENCE = 0.3


class RelationsAgent:
    def __init__(
        self,
        ontology: OntologyIndex,
        extractor: SVOExtractor | None = None,
        lexicon: InverseVerbLexicon | None = None,
    ):
        self.ontology = ontology
        self.lexicon = lexicon if lexicon is not None else InverseVerbLexicon.from_ontology(ontology)
        self.extractor = extractor if extractor is not None else RegexHeuristicExtractor()

    def evaluate(self, term: EnrichedTerm) -> list[SemanticRelation]:
        subject_uri = self._resolve_subject_uri(term)
        if subject_uri is None:
            raise ValueError(
                "EnrichedTerm has no resolvable subject URI — Relations agent needs "
                "either match_result.target_uri, taxonomy_placement.domain_prefix, or "
                "candidate_labels to anchor the subject."
            )
        text = self._collect_text(term)
        if not text:
            return []
        triples = self.extractor.extract(text, default_subject=term.preferred_label)
        return [self._to_relation(t, subject_uri) for t in triples]

    def apply(self, term: EnrichedTerm) -> EnrichedTerm:
        term.relations = self.evaluate(term)
        return term

    def _resolve_subject_uri(self, term: EnrichedTerm) -> str | None:
        if term.match_result and term.match_result.target_uri:
            return term.match_result.target_uri
        if term.taxonomy_placement and term.taxonomy_placement.domain_prefix:
            return term.taxonomy_placement.domain_prefix
        if term.preferred_label:
            return f"_:candidate/{term.preferred_label.replace(' ', '_')}"
        return None

    @staticmethod
    def _collect_text(term: EnrichedTerm) -> str:
        parts: list[str] = []
        if term.definition:
            parts.append(term.definition)
        for ctx in term.policy_context:
            if ctx.paragraph:
                parts.append(ctx.paragraph)
        return " ".join(parts).strip()

    def _to_relation(self, triple: SVOTriple, subject_uri: str) -> SemanticRelation:
        lookup = self.lexicon.lookup(triple.verb)
        if lookup is None:
            return SemanticRelation(
                subject_uri=subject_uri,
                predicate_uri=None,
                object_label=triple.object,
                inverse_predicate_uri=None,
                verb=triple.verb,
                confidence=min(triple.confidence, UNRESOLVED_VERB_CONFIDENCE),
                status=RelationStatus.UNRESOLVED_VERB,
            )
        return SemanticRelation(
            subject_uri=subject_uri,
            predicate_uri=lookup.predicate_uri,
            object_label=triple.object,
            inverse_predicate_uri=lookup.inverse_predicate_uri,
            verb=triple.verb,
            confidence=triple.confidence,
            status=RelationStatus.RESOLVED,
        )
