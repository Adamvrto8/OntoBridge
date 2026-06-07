from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from ontobridge.agents.definition.agent import LLMDefinitionAgent
from ontobridge.agents.fibo.matcher import FiboMatcher
from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.agents.harvester.agent import HarvesterAgent
from ontobridge.agents.policy_linker import PolicyLinkerAgent, TFIDFPolicyLinker

AnyPolicyLinker = PolicyLinkerAgent | TFIDFPolicyLinker
from ontobridge.models.enrichment import CandidateLabel, EnrichedTerm
from ontobridge.models.published import PublishedTerm
from ontobridge.pipeline import PipelineRunner
from ontobridge.pipeline_config import PipelineConfig
from ontobridge.publisher.base import TermPublisher


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class FailedTerm:
    """A term that could not be processed due to an unexpected error."""
    term: EnrichedTerm
    error_type: str   # exception class name
    error: str        # str(exception)


@dataclass
class BatchResult:
    """Aggregated outcome of a batch pipeline run.

    Attributes:
        published: Brand-new terms that completed the pipeline and were stored.
        merged:    Terms that already existed; the document was folded in as
                   provenance (and any new synonyms). No review needed.
        drifted:   Existing terms the document defines differently — folded in
                   and flagged for steward review.
        skipped:   Terms rejected at input validation (missing labels /
                   definition) or whose URI already exists in the publisher.
        failed:    Terms that raised an unexpected exception mid-pipeline.
    """
    published: list[PublishedTerm] = field(default_factory=list)
    merged: list[PublishedTerm] = field(default_factory=list)
    drifted: list[PublishedTerm] = field(default_factory=list)
    skipped: list[tuple[EnrichedTerm, str]] = field(default_factory=list)
    failed: list[FailedTerm] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def total(self) -> int:
        return (
            len(self.published) + len(self.merged) + len(self.drifted)
            + len(self.skipped) + len(self.failed)
        )

    @property
    def success_rate(self) -> float:
        ok = len(self.published) + len(self.merged) + len(self.drifted)
        return ok / self.total if self.total else 0.0

    def summary(self) -> str:
        return (
            f"BatchResult: {len(self.published)} published, "
            f"{len(self.merged)} merged, "
            f"{len(self.drifted)} drifted, "
            f"{len(self.skipped)} skipped, "
            f"{len(self.failed)} failed "
            f"(total={self.total}, success={self.success_rate:.0%})"
        )

    def __repr__(self) -> str:
        return self.summary()


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

# Signature: (processed_so_far, total) → None
ProgressCallback = Callable[[int, int], None]


class BatchPipelineRunner:
    """Runs multiple terms or documents through the pipeline in sequence.

    Each term is processed independently — a failure on one term does not
    abort the rest.  Results are collected into a ``BatchResult``.

    Error handling
    --------------
    - ``ValueError`` from input validation (missing labels / definition)
      → term is placed in ``BatchResult.skipped`` with a reason string.
    - Duplicate URI already in the publisher
      → term is placed in ``BatchResult.skipped``.
    - Any other exception
      → term is placed in ``BatchResult.failed`` with the error captured.

    Args:
        ontology:    OntologyIndex shared by all pipeline agents.
        publisher:   Where approved terms are persisted.
        config:      Full pipeline configuration (thresholds, encoder, namespaces).
        harvester:   HarvesterAgent used by ``run_documents()``.  A default
                     instance (all readers, PatternTermExtractor) is created
                     when omitted.
        on_progress: Optional callback ``(processed, total) -> None`` called
                     after every term.  Useful for Streamlit progress bars.
    """

    def __init__(
        self,
        ontology: OntologyIndex,
        publisher: TermPublisher,
        config: PipelineConfig | None = None,
        harvester: HarvesterAgent | None = None,
        on_progress: ProgressCallback | None = None,
        policy_linker: AnyPolicyLinker | None = None,
        definition_agent: LLMDefinitionAgent | None = None,
        fibo_matcher: FiboMatcher | None = None,
        llm_backend=None,
    ) -> None:
        self._runner = PipelineRunner(
            ontology, publisher,
            config=config,
            policy_linker=policy_linker,
            definition_agent=definition_agent,
            fibo_matcher=fibo_matcher,
            llm_backend=llm_backend,
        )
        self._harvester = harvester or HarvesterAgent()
        self._on_progress = on_progress

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def run_terms(
        self,
        terms: Sequence[EnrichedTerm],
        *,
        approved_by: str | None = None,
    ) -> BatchResult:
        """Process a pre-harvested list of EnrichedTerms through the pipeline."""
        result = BatchResult()
        deduped = self._deduplicate_by_fibo(list(terms), result)
        total = len(deduped)
        for i, term in enumerate(deduped):
            self._process_one(term, result, approved_by=approved_by)
            if self._on_progress:
                self._on_progress(i + 1, total)
        return result

    def run_document(
        self,
        source: Path | str,
        *,
        source_system: str = "harvester",
        document_id: str | None = None,
        approved_by: str | None = None,
    ) -> BatchResult:
        """Harvest a single document and run all extracted terms through the pipeline."""
        terms = self._harvester.harvest_terms(
            source, source_system=source_system, document_id=document_id
        )
        return self.run_terms(terms, approved_by=approved_by)

    def run_documents(
        self,
        sources: Sequence[Path | str],
        *,
        source_system: str = "harvester",
        approved_by: str | None = None,
    ) -> BatchResult:
        """Harvest multiple documents and run all extracted terms through the pipeline.

        Terms are globally deduplicated by record_id before the pipeline runs,
        so the same passage appearing in two documents is only processed once.
        """
        seen_ids: set[str] = set()
        all_terms: list[EnrichedTerm] = []

        for source in sources:
            for term in self._harvester.harvest_terms(
                source, source_system=source_system
            ):
                record_id = term.harvest_record.record_id
                if record_id not in seen_ids:
                    seen_ids.add(record_id)
                    all_terms.append(term)

        return self.run_terms(all_terms, approved_by=approved_by)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    _MATCH_RANK: dict[str, int] = {"exact": 0, "close": 1, "broad": 2}

    def _deduplicate_by_fibo(
        self,
        terms: list[EnrichedTerm],
        result: BatchResult,
    ) -> list[EnrichedTerm]:
        """Merge terms that map to the same FIBO URI into the best-matched one.

        The winner is the term with the highest-quality FIBO match (exact >
        close > broad).  Loser labels are folded into the winner's
        candidate_labels at reduced confidence so they appear as alt_labels.
        Losers are added to BatchResult.skipped with a merge reason.
        """
        by_fibo: dict[str, list[EnrichedTerm]] = {}
        no_fibo: list[EnrichedTerm] = []

        for term in terms:
            if term.fibo_match:
                by_fibo.setdefault(term.fibo_match.uri, []).append(term)
            else:
                no_fibo.append(term)

        deduped: list[EnrichedTerm] = list(no_fibo)

        for fibo_uri, group in by_fibo.items():
            if len(group) == 1:
                deduped.append(group[0])
                continue

            group.sort(key=lambda t: (
                self._MATCH_RANK.get(t.fibo_match.match_type, 3),  # type: ignore[union-attr]
                -max((c.confidence for c in t.candidate_labels), default=0.0),
            ))
            winner, *losers = group

            existing = {c.text.lower() for c in winner.candidate_labels}
            for loser in losers:
                for lbl in loser.candidate_labels:
                    if lbl.text.lower() not in existing:
                        winner.candidate_labels.append(
                            CandidateLabel(
                                text=lbl.text,
                                confidence=lbl.confidence * 0.8,
                                ner_label=lbl.ner_label,
                            )
                        )
                        existing.add(lbl.text.lower())
                result.skipped.append((
                    loser,
                    f"merged into '{winner.preferred_label}' (same FIBO URI: {fibo_uri})",
                ))

            deduped.append(winner)

        return deduped

    def _process_one(
        self,
        term: EnrichedTerm,
        result: BatchResult,
        *,
        approved_by: str | None,
    ) -> None:
        label = term.preferred_label or "(unlabelled)"
        try:
            outcome = self._runner.ingest(term, approved_by=approved_by)
            if outcome.action == "merged":
                result.merged.append(outcome.term)
            elif outcome.action == "drifted":
                result.drifted.append(outcome.term)
            else:
                result.published.append(outcome.term)
        except ValueError as exc:
            msg = str(exc)
            # Duplicate URI from the publisher → skipped, not a failure
            if "already exists" in msg or "candidate_labels" in msg or "definition" in msg:
                result.skipped.append((term, msg))
            else:
                result.failed.append(
                    FailedTerm(term=term, error_type="ValueError", error=msg)
                )
        except Exception as exc:  # noqa: BLE001
            result.failed.append(
                FailedTerm(
                    term=term,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
