from __future__ import annotations

from ontobridge.agents.definition.extractor import HeuristicDefinitionExtractor
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
