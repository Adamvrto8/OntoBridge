from __future__ import annotations

from difflib import SequenceMatcher

from ontobridge.agents.governance import Candidate, GovernanceAgent, PolicyRef
from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.agents.mapping import MappingAgent, from_ontology
from ontobridge.agents.mapping.glossary import GlossarySource
from ontobridge.agents.mapping.strategies import Encoder
from ontobridge.agents.definition.agent import LLMDefinitionAgent
from ontobridge.agents.policy_linker import PolicyLinkerAgent
from ontobridge.agents.relations import RelationsAgent
from ontobridge.agents.taxonomy import TaxonomyAgent
from ontobridge.agents.writer import WriterAgent
from ontobridge.models.enrichment import EnrichedTerm
from ontobridge.models.enums import RelationStatus
from ontobridge.models.published import PublishedTerm
from ontobridge.pipeline_config import PipelineConfig
from ontobridge.publisher.base import TermPublisher

_OBJECT_RESOLUTION_THRESHOLD = 0.82


class PipelineRunner:
    """Chains Mapping → Taxonomy → Relations → Governance → Writer.

    Callers must supply an EnrichedTerm with ``candidate_labels`` and
    ``definition`` already populated — use ``HarvesterAgent.harvest_terms()``
    to produce these from a document, or populate them manually.

    ``policy_context`` and ``fibo_match`` are optional and flow through when
    present.

    Args:
        ontology: The OntologyIndex used by all agents.
        publisher: Where approved terms are persisted.
        glossary: Override the default ontology-derived glossary used by
            MappingAgent.  Useful when you want to match against a richer
            or different term set.
        encoder: Optional dense encoder (e.g. SentenceTransformerEncoder)
            shared by MappingAgent and TaxonomyAgent.  Defaults to the
            TokenOverlapEncoder fallback when omitted.  Ignored when
            ``config`` is provided (config.encoder takes precedence).
        config: Optional PipelineConfig with all thresholds and namespaces.
            When supplied, individual keyword arguments are ignored.
    """

    def __init__(
        self,
        ontology: OntologyIndex,
        publisher: TermPublisher,
        glossary: GlossarySource | None = None,
        encoder: Encoder | None = None,
        config: PipelineConfig | None = None,
        policy_linker: PolicyLinkerAgent | None = None,
        definition_agent: LLMDefinitionAgent | None = None,
    ):
        cfg = config or PipelineConfig(encoder=encoder)

        self.ontology = ontology
        self.publisher = publisher
        self.config = cfg
        self.policy_linker = policy_linker
        self.definition_agent = definition_agent
        self.glossary: GlossarySource = (
            glossary if glossary is not None else from_ontology(ontology)
        )
        self.mapping = MappingAgent(
            self.glossary,
            fuzzy_threshold=cfg.fuzzy_threshold,
            embedding_threshold=cfg.embedding_threshold,
            encoder=cfg.encoder,
        )
        self.taxonomy = TaxonomyAgent(
            ontology,
            encoder=cfg.encoder,
            placement_threshold=cfg.placement_threshold,
            sibling_conflict_threshold=cfg.sibling_conflict_threshold,
        )
        self.relations = RelationsAgent(ontology)
        self.governance = GovernanceAgent(ontology)
        self.writer = WriterAgent(
            publisher,
            ontology=ontology,
            bank_namespace=cfg.bank_namespace,
            rel_namespace=cfg.rel_namespace,
        )

    def run(
        self,
        term: EnrichedTerm,
        *,
        term_uri: str | None = None,
        approved_by: str | None = None,
    ) -> PublishedTerm:
        self._validate_input(term)
        if self.policy_linker is not None:
            self.policy_linker.apply(term)
        self.mapping.apply(term)
        self.taxonomy.apply(term)
        if self.definition_agent is not None:
            self.definition_agent.apply(term)
        self.relations.apply(term)
        self._resolve_relation_objects(term)
        candidate = self._term_to_candidate(term)
        term.governance_result = self.governance.evaluate(candidate)
        return self.writer.publish(term, term_uri=term_uri, approved_by=approved_by)

    def _resolve_relation_objects(self, term: EnrichedTerm) -> None:
        """Try to link each relation's object_label to a published term URI."""
        for rel in term.relations:
            if rel.object_uri is not None:
                continue  # already resolved (e.g. FIBO closeMatch)
            if rel.status is RelationStatus.FIBO_MATCH:
                continue
            if not rel.object_label or rel.object_label == "—":
                continue
            uri = self._find_term_uri(rel.object_label)
            if uri:
                rel.object_uri = uri

    def _find_term_uri(self, object_label: str) -> str | None:
        needle = object_label.casefold().strip()
        if not needle:
            return None
        candidates = self.publisher.search_terms(needle)
        best_uri: str | None = None
        best_score = 0.0
        for published in candidates:
            pref = (published.enriched_term.preferred_label or "").casefold()
            if pref == needle:
                return published.term_uri  # exact match — done
            score = SequenceMatcher(None, needle, pref).ratio()
            if score > best_score:
                best_score = score
                best_uri = published.term_uri
        if best_score >= _OBJECT_RESOLUTION_THRESHOLD:
            return best_uri
        return None

    @staticmethod
    def _validate_input(term: EnrichedTerm) -> None:
        if not term.candidate_labels:
            raise ValueError(
                "PipelineRunner requires term.candidate_labels to be populated "
                "(NER agent is skipped — caller must seed labels)."
            )
        if not term.definition:
            raise ValueError(
                "PipelineRunner requires term.definition to be populated "
                "(Definition agent is skipped — caller must seed the definition)."
            )

    @staticmethod
    def _term_to_candidate(term: EnrichedTerm) -> Candidate:
        scheme = (
            term.taxonomy_placement.scheme_uri
            if term.taxonomy_placement and term.taxonomy_placement.scheme_uri
            else None
        )
        policy_refs = [
            PolicyRef(document=p.document_ref, section=p.section, snippet=p.paragraph)
            for p in term.policy_context
        ]
        return Candidate(
            preferred_label=term.preferred_label or "",
            domain=scheme,
            definition=term.definition,
            policy_refs=policy_refs,
            fibo_match=term.fibo_match,
        )
