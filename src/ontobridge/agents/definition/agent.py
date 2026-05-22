from __future__ import annotations

from ontobridge.agents.definition.extractor import HeuristicDefinitionExtractor
from ontobridge.models.enrichment import EnrichedTerm
from ontobridge.models.source import HarvestRecord


class DefinitionAgent:
    """Extracts a clean definition sentence from a HarvestRecord.

    Uses HeuristicDefinitionExtractor by default.  Falls back to the full
    record text when extraction returns nothing so that downstream agents
    always receive a non-empty definition.
    """

    def __init__(self, extractor: HeuristicDefinitionExtractor | None = None) -> None:
        self._extractor = extractor or HeuristicDefinitionExtractor()

    def extract(self, record: HarvestRecord, label: str | None = None) -> str:
        result = self._extractor.extract(record.text, label=label)
        return result if result else record.text


class LLMDefinitionAgent:
    """Improves term definitions and generates IF...THEN business rules via LLM.

    Runs in PipelineRunner after TaxonomyAgent (needs placement context) and
    before RelationsAgent and GovernanceAgent (both consume the final definition).

    On success:
    - ``term.definition`` is replaced with a plain-language LLM definition.
    - ``term.business_rules`` is populated with 2–3 IF...THEN rules.

    On LLM failure or malformed response the original ``term.definition`` is
    kept unchanged and ``term.business_rules`` stays empty — the pipeline never
    crashes due to a bad LLM response.

    Args:
        backend:              LLM backend — reuse the same instance as NER agent
                              to avoid loading a second model.
        min_definition_words: Minimum word count for the generated definition
                              to be accepted (default 10, mirrors Governance Rule 08).
    """

    def __init__(self, backend, min_definition_words: int = 10) -> None:
        if min_definition_words < 0:
            raise ValueError("min_definition_words must be >= 0")
        self._backend = backend
        self._min_definition_words = min_definition_words

    def apply(self, term: EnrichedTerm) -> None:
        """Generate and attach an improved definition + business rules to *term*."""
        from ontobridge.agents.definition.prompt import (
            SYSTEM_PROMPT,
            build_user_prompt,
            extract_business_rules,
            extract_definition,
            parse_response,
        )

        if not term.preferred_label:
            return

        response = self._backend.complete(
            system=SYSTEM_PROMPT,
            user=build_user_prompt(term),
        )
        data = parse_response(response)
        if not data:
            return

        definition = extract_definition(data, min_words=self._min_definition_words)
        if definition:
            term.definition = definition
            term.definition_source = "llm"

        rules = extract_business_rules(data)
        if rules:
            term.business_rules = rules
