from __future__ import annotations

import logging

from ontobridge.agents.fibo.matcher import FiboMatcher, FiboRelation
from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.agents.relations.extractor import (
    RegexHeuristicExtractor,
    SVOExtractor,
    SVOTriple,
)
from ontobridge.agents.relations.lexicon import InverseVerbLexicon
from ontobridge.models.enrichment import EnrichedTerm, SemanticRelation
from ontobridge.models.enums import RelationStatus
from ontobridge.models.fibo import FIBOMatch

_log = logging.getLogger(__name__)

UNRESOLVED_VERB_CONFIDENCE = 0.3
_SKOS_CLOSE_MATCH = "http://www.w3.org/2004/02/skos/core#closeMatch"
_SKOS_EXACT_MATCH = "http://www.w3.org/2004/02/skos/core#exactMatch"


class RelationsAgent:
    def __init__(
        self,
        ontology: OntologyIndex,
        extractor: SVOExtractor | None = None,
        lexicon: InverseVerbLexicon | None = None,
        fibo_matcher: FiboMatcher | None = None,
        llm_backend=None,
        feedback_store=None,
    ):
        self.ontology = ontology
        self.lexicon = lexicon if lexicon is not None else InverseVerbLexicon.from_ontology(ontology)
        self.extractor = extractor if extractor is not None else RegexHeuristicExtractor()
        self.fibo_matcher = fibo_matcher
        self.llm_backend = llm_backend
        self.feedback_store = feedback_store

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
        subject_uri = self._resolve_subject_uri(term)
        if subject_uri is None:
            raise ValueError(
                "EnrichedTerm has no resolvable subject URI — Relations agent needs "
                "either match_result.target_uri, taxonomy_placement.domain_prefix, or "
                "candidate_labels to anchor the subject."
            )
        relations: list[SemanticRelation] = []

        # Text-based SVO extraction (always runs)
        text = self._collect_text(term)
        if text:
            seen: set[tuple[str, str]] = set()
            for t in self.extractor.extract(text, default_subject=term.preferred_label):
                key = (t.verb, t.object)
                if key not in seen:
                    seen.add(key)
                    relations.append(self._to_relation(t, subject_uri))

        # FIBO-based relations (when matcher available and FIBO match exists)
        fibo_rels: list[FiboRelation] = []
        if term.fibo_match and self.fibo_matcher:
            fibo_rels = self.fibo_matcher.relations_for_uri(term.fibo_match.uri)
            match_type = term.fibo_match.match_type

            if match_type == "exact":
                resolved, fallback = self._fibo_as_resolved(fibo_rels, subject_uri)
                relations.extend(resolved)
                relations.extend(fallback)
            else:
                relations.extend(self._fibo_as_proposed(fibo_rels, subject_uri))

            relations.append(self._fibo_close_match_relation(term.fibo_match, subject_uri))

        elif term.fibo_match:
            relations.append(self._fibo_close_match_relation(term.fibo_match, subject_uri))

        # Inherited FIBO relations from broader concept (when no direct FIBO match)
        inherited_fibo_rels: list[FiboRelation] = []
        if not term.fibo_match and self.fibo_matcher and term.taxonomy_placement:
            broader_uri = term.taxonomy_placement.broader_concept_uri
            if broader_uri:
                broader_label = broader_uri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
                broader_fibo = self.fibo_matcher.match(broader_label)
                if broader_fibo:
                    inherited_fibo_rels = self.fibo_matcher.relations_for_uri(broader_fibo.uri)
                    for r in inherited_fibo_rels:
                        relations.append(SemanticRelation(
                            subject_uri=subject_uri,
                            predicate_uri=r.property_uri,
                            object_label=r.range_label or r.range_uri.rsplit("/", 1)[-1],
                            object_uri=r.range_uri,
                            inverse_predicate_uri=r.inverse_uri,
                            verb=r.property_label or r.property_uri.rsplit("/", 1)[-1],
                            confidence=0.6,
                            status=RelationStatus.PROPOSED,
                            source="fibo",
                        ))

        # LLM proposes additional relations for all terms when backend is available
        if self.llm_backend is not None:
            match_type_for_llm = term.fibo_match.match_type if term.fibo_match else "none"
            relations.extend(
                self._llm_propose(term, fibo_rels + inherited_fibo_rels, subject_uri, match_type_for_llm)
            )

        term.relations = relations
        return term

    # ---- FIBO relation builders ----------------------------------------

    def _fibo_as_resolved(
        self, fibo_rels: list[FiboRelation], subject_uri: str
    ) -> tuple[list[SemanticRelation], list[SemanticRelation]]:
        """Returns (resolved, proposed_fallback) — relations without inverse go to fallback."""
        resolved: list[SemanticRelation] = []
        fallback: list[SemanticRelation] = []
        for r in fibo_rels:
            if r.inverse_uri:
                resolved.append(SemanticRelation(
                    subject_uri=subject_uri,
                    predicate_uri=r.property_uri,
                    object_label=r.range_label or r.range_uri.rsplit("/", 1)[-1],
                    object_uri=r.range_uri,
                    inverse_predicate_uri=r.inverse_uri,
                    verb=r.property_label or r.property_uri.rsplit("/", 1)[-1],
                    confidence=0.9,
                    status=RelationStatus.RESOLVED,
                    source="fibo",
                ))
            else:
                fallback.append(SemanticRelation(
                    subject_uri=subject_uri,
                    predicate_uri=r.property_uri,
                    object_label=r.range_label or r.range_uri.rsplit("/", 1)[-1],
                    object_uri=r.range_uri,
                    inverse_predicate_uri=None,
                    verb=r.property_label or r.property_uri.rsplit("/", 1)[-1],
                    confidence=0.75,
                    status=RelationStatus.PROPOSED,
                    source="fibo",
                ))
        return resolved, fallback

    def _fibo_as_proposed(
        self, fibo_rels: list[FiboRelation], subject_uri: str
    ) -> list[SemanticRelation]:
        result: list[SemanticRelation] = []
        for r in fibo_rels:
            result.append(SemanticRelation(
                subject_uri=subject_uri,
                predicate_uri=r.property_uri,
                object_label=r.range_label or r.range_uri.rsplit("/", 1)[-1],
                object_uri=r.range_uri,
                inverse_predicate_uri=r.inverse_uri,
                verb=r.property_label or r.property_uri.rsplit("/", 1)[-1],
                confidence=0.7,
                status=RelationStatus.PROPOSED,
                source="fibo",
            ))
        return result

    def _llm_propose(
        self,
        term: EnrichedTerm,
        fibo_rels: list[FiboRelation],
        subject_uri: str,
        match_type: str,
    ) -> list[SemanticRelation]:
        from ontobridge.agents.relations.fibo_prompt import (
            SYSTEM_PROMPT,
            build_user_prompt,
            parse_response,
        )
        approved = (
            self.feedback_store.get_examples("relation_approved")
            if self.feedback_store else []
        )
        rejected = (
            self.feedback_store.get_examples("relation_rejected")
            if self.feedback_store else []
        )
        try:
            response = self.llm_backend.complete(
                system=SYSTEM_PROMPT,
                user=build_user_prompt(term, fibo_rels, match_type, approved=approved, rejected=rejected),
            )
            proposals = parse_response(response)
        except Exception as exc:
            _log.warning(
                "LLM relation proposal failed for %r: %s: %s",
                term.preferred_label, type(exc).__name__, exc,
            )
            return []

        result: list[SemanticRelation] = []
        for p in proposals:
            lookup = self.lexicon.lookup(p["verb"])
            result.append(SemanticRelation(
                subject_uri=subject_uri,
                predicate_uri=lookup.predicate_uri if lookup else None,
                object_label=p["object"],
                inverse_predicate_uri=lookup.inverse_predicate_uri if lookup else None,
                verb=p["verb"],
                confidence=0.5,
                status=RelationStatus.PROPOSED,
                source="llm",
            ))
        return result

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
        defn = term.definition or ""
        if defn:
            parts.append(defn)
        defn_cf = defn.casefold()
        for ctx in term.policy_context:
            para = (ctx.paragraph or "").strip()
            if not para:
                continue
            # Skip if the paragraph is the same as or fully contained in the definition
            if para.casefold() in defn_cf:
                continue
            parts.append(para)
        return " ".join(parts).strip()

    @staticmethod
    def _fibo_close_match_relation(fibo_match: FIBOMatch, subject_uri: str) -> SemanticRelation:
        label = fibo_match.uri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        is_exact = fibo_match.match_type == "exact"
        pred = _SKOS_EXACT_MATCH if is_exact else _SKOS_CLOSE_MATCH
        verb = "exactMatch" if is_exact else "closeMatch"
        return SemanticRelation(
            subject_uri=subject_uri,
            predicate_uri=pred,
            object_label=label or fibo_match.uri,
            object_uri=fibo_match.uri,
            inverse_predicate_uri=pred,
            verb=verb,
            confidence=0.9,
            status=RelationStatus.FIBO_MATCH,
        )

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
                source="svo",
            )
        return SemanticRelation(
            subject_uri=subject_uri,
            predicate_uri=lookup.predicate_uri,
            object_label=triple.object,
            inverse_predicate_uri=lookup.inverse_predicate_uri,
            verb=triple.verb,
            confidence=triple.confidence,
            status=RelationStatus.RESOLVED,
            source="svo",
        )
