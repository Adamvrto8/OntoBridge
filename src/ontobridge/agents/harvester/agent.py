from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ontobridge.agents.harvester.extractors.pattern import PatternTermExtractor
from ontobridge.agents.harvester.protocols import DocumentReader, TermExtractor
from ontobridge.agents.harvester.readers.catalog import CatalogReader
from ontobridge.agents.harvester.readers.docx import DocxReader
from ontobridge.agents.harvester.readers.pdf import PdfReader
from ontobridge.agents.harvester.readers.text import PlainTextReader
from ontobridge.models import CandidateLabel, EnrichedTerm
from ontobridge.models.enrichment import PolicyContext
from ontobridge.models.enums import SourceType, Tier
from ontobridge.models.source import HarvestRecord, SourceRef

# Maps SourceType to the Tier that makes semantic sense for that source
_SOURCE_TIER: dict[SourceType, Tier] = {
    SourceType.CATALOG: Tier.STRUCTURED,
    SourceType.POLICY_DOC: Tier.DOCUMENT,
    SourceType.CONTRACT: Tier.DOCUMENT,
    SourceType.WIKI: Tier.DOCUMENT,
    SourceType.DATA_PRODUCT: Tier.STRUCTURED,
    SourceType.COMMUNICATION: Tier.UNSTRUCTURED,
    SourceType.USER_INPUT: Tier.UNSTRUCTURED,
}


def _default_readers() -> list[DocumentReader]:
    return [PlainTextReader(), PdfReader(), DocxReader(), CatalogReader()]


def _policy_context_from_record(record: HarvestRecord) -> PolicyContext:
    """Build a PolicyContext from a HarvestRecord's source reference.

    Uses document_id when available, falls back to source_system so that
    PolicyContext.document_ref is always non-empty (as required by its
    validator) and governance rule R10 does not fire on harvested terms.
    """
    return PolicyContext(
        paragraph=record.text,
        document_ref=record.source_ref.document_id or record.source_ref.source_system,
        section=record.source_ref.section,
    )


class HarvesterAgent:
    """Reads one or more source documents and produces HarvestRecords.

    Architecture
    ------------
    - A list of ``DocumentReader`` instances covers different file formats.
      ``can_read()`` is called in order; the first match wins.
    - A single ``TermExtractor`` scans each RawDocument chunk for
      (candidate_label, definition) pairs.
    - Results are deduplicated by ``HarvestRecord.record_id`` (SHA-256 of
      text + source fingerprint) so the same term found twice in one document
      is returned only once.

    Plugging in new sources
    -----------------------
    Implement the ``DocumentReader`` protocol and pass it in ``readers``.
    No other code changes — the rest of the pipeline is untouched.

    Plugging in NLP extraction
    --------------------------
    Implement the ``TermExtractor`` protocol (e.g. spaCy NER) and pass it as
    ``extractor``.  The default ``PatternTermExtractor`` stays as the fallback.
    """

    def __init__(
        self,
        readers: Sequence[DocumentReader] | None = None,
        extractor: TermExtractor | None = None,
    ) -> None:
        self.readers: list[DocumentReader] = list(readers) if readers else _default_readers()
        self.extractor: TermExtractor = extractor or PatternTermExtractor()

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def harvest(
        self,
        source: Path | str,
        *,
        source_system: str = "harvester",
        document_id: str | None = None,
    ) -> list[HarvestRecord]:
        """Read *source* and return deduplicated HarvestRecords.

        Args:
            source: File path (str or Path).  Passed unchanged to the reader.
            source_system: Logical name for the originating system
                (e.g. ``"policy_repo"``, ``"unity_catalog"``).
            document_id: Optional explicit document identifier.  Defaults to
                the basename of *source*.
        """
        reader = self._find_reader(source)
        docs = reader.read(source)
        doc_id = document_id or Path(source).name

        records: list[HarvestRecord] = []
        seen: set[str] = set()

        for doc in docs:
            for term in self.extractor.extract(doc):
                ref = SourceRef(
                    source_system=source_system,
                    document_id=doc_id,
                    section=term.section or doc.section,
                )
                record = HarvestRecord(
                    text=term.definition,
                    source_type=reader.source_type,
                    source_ref=ref,
                    confidence=term.confidence,
                    tier=_SOURCE_TIER.get(reader.source_type, Tier.DOCUMENT),
                    metadata={"candidate_label": term.candidate_label, **term.metadata},
                )
                if record.record_id not in seen:
                    seen.add(record.record_id)
                    records.append(record)

        return records

    def harvest_terms(
        self,
        source: Path | str,
        *,
        source_system: str = "harvester",
        document_id: str | None = None,
    ) -> list[EnrichedTerm]:
        """Harvest and lift records into EnrichedTerm objects ready for PipelineRunner.

        Each returned term has ``candidate_labels`` and ``definition``
        pre-populated so it can be passed directly to ``PipelineRunner.run()``.
        """
        terms: list[EnrichedTerm] = []
        for record in self.harvest(
            source, source_system=source_system, document_id=document_id
        ):
            term = EnrichedTerm.from_harvest(record)
            term.definition = record.text
            label = record.metadata.get("candidate_label", "")
            if label:
                term.candidate_labels = [
                    CandidateLabel(text=label, confidence=record.confidence)
                ]
            term.policy_context = [_policy_context_from_record(record)]
            terms.append(term)
        return terms

    # ------------------------------------------------------------------
    # Multi-source convenience
    # ------------------------------------------------------------------

    def harvest_all(
        self,
        sources: Sequence[Path | str],
        *,
        source_system: str = "harvester",
    ) -> list[HarvestRecord]:
        """Harvest multiple sources and return a globally deduplicated list."""
        seen: set[str] = set()
        all_records: list[HarvestRecord] = []
        for source in sources:
            for record in self.harvest(source, source_system=source_system):
                if record.record_id not in seen:
                    seen.add(record.record_id)
                    all_records.append(record)
        return all_records

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_reader(self, source: Path | str) -> DocumentReader:
        for reader in self.readers:
            if reader.can_read(source):
                return reader
        suffix = Path(source).suffix
        raise ValueError(
            f"No reader registered for {suffix!r}. "
            f"Available readers: {[type(r).__name__ for r in self.readers]}"
        )
