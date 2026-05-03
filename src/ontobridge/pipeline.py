from __future__ import annotations

from ontobridge.agents.governance import Candidate, GovernanceAgent, PolicyRef
from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.agents.mapping import MappingAgent, from_ontology
from ontobridge.agents.mapping.glossary import GlossarySource
from ontobridge.agents.relations import RelationsAgent
from ontobridge.agents.taxonomy import TaxonomyAgent
from ontobridge.agents.writer import WriterAgent
from ontobridge.models.enrichment import EnrichedTerm
from ontobridge.models.published import PublishedTerm
from ontobridge.publisher.base import TermPublisher


class PipelineRunner:
    """Chains the four currently-built agents:
    Mapping → Taxonomy → Relations → Governance → Writer.

    The runner skips NER, Policy Linker, and Definition. Callers must supply an
    EnrichedTerm with `candidate_labels` and `definition` already populated;
    `policy_context` and `fibo_match` are optional but flow through the agents
    when present.
    """

    def __init__(
        self,
        ontology: OntologyIndex,
        publisher: TermPublisher,
        glossary: GlossarySource | None = None,
    ):
        self.ontology = ontology
        self.publisher = publisher
        self.glossary: GlossarySource = (
            glossary if glossary is not None else from_ontology(ontology)
        )
        self.mapping = MappingAgent(self.glossary)
        self.taxonomy = TaxonomyAgent(ontology)
        self.relations = RelationsAgent(ontology)
        self.governance = GovernanceAgent(ontology)
        self.writer = WriterAgent(publisher, ontology=ontology)

    def run(
        self,
        term: EnrichedTerm,
        *,
        term_uri: str | None = None,
        approved_by: str | None = None,
    ) -> PublishedTerm:
        self._validate_input(term)
        self.mapping.apply(term)
        self.taxonomy.apply(term)
        self.relations.apply(term)
        candidate = self._term_to_candidate(term)
        term.governance_result = self.governance.evaluate(candidate)
        return self.writer.publish(term, term_uri=term_uri, approved_by=approved_by)

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
