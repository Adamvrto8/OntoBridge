from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
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
        max_workers: int = 1,
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
        # >1 enables the concurrent path: per-term LLM enrichment runs in a
        # thread pool while dedup/publish stays serial. Default 1 = fully
        # sequential (unchanged behaviour).
        self._max_workers = max(1, max_workers)

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
        if self._max_workers > 1:
            return self._run_terms_concurrent(deduped, result, approved_by=approved_by)
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
        try:
            outcome = self._runner.ingest(term, approved_by=approved_by)
            self._record_outcome(result, outcome.action, outcome.term)
        except Exception as exc:  # noqa: BLE001
            self._record_error(result, term, exc)

    @staticmethod
    def _record_outcome(result: BatchResult, action: str, term: PublishedTerm) -> None:
        if action == "merged":
            result.merged.append(term)
        elif action == "drifted":
            result.drifted.append(term)
        else:
            result.published.append(term)

    @staticmethod
    def _record_error(result: BatchResult, term: EnrichedTerm, exc: Exception) -> None:
        msg = str(exc)
        # Input-validation / duplicate-URI ValueErrors are expected → skipped.
        if isinstance(exc, ValueError) and (
            "already exists" in msg or "candidate_labels" in msg or "definition" in msg
        ):
            result.skipped.append((term, msg))
        else:
            result.failed.append(
                FailedTerm(term=term, error_type=type(exc).__name__, error=msg)
            )

    # ------------------------------------------------------------------
    # Concurrent path (max_workers > 1): enrich in parallel, publish serially
    # ------------------------------------------------------------------

    def _run_terms_concurrent(
        self,
        deduped: list[EnrichedTerm],
        result: BatchResult,
        *,
        approved_by: str | None,
    ) -> BatchResult:
        # Phase 0 — serial prepare (mapping reads the publisher) + classify.
        merges: list[tuple[EnrichedTerm, PublishedTerm]] = []
        creates: list[EnrichedTerm] = []
        for term in deduped:
            try:
                self._runner._prepare(term)
            except Exception as exc:  # noqa: BLE001 — validation errors → skipped
                self._record_error(result, term, exc)
                continue
            existing = self._runner._existing_published_target(term)
            if existing is not None:
                merges.append((term, existing))
            else:
                creates.append(term)

        # Phase 0b — fold within-batch duplicate new terms into one winner so we
        # don't enrich/publish the same concept twice (FIBO dedup already handled
        # FIBO-identical terms; this catches same-label terms across documents).
        winners = self._dedup_new_terms_by_label(creates, result)

        # Phase A — enrich winners concurrently (the LLM-heavy, publisher-free work).
        errors = self._enrich_concurrent(winners)

        # Phase B — serial publish + merge (no publisher write races).
        total = len(winners) + len(merges)
        done = 0
        for term in winners:
            try:
                exc = errors.get(id(term))
                if exc is not None:
                    raise exc
                published = self._runner._commit(term, approved_by=approved_by)
                self._record_outcome(result, "created", published)
            except Exception as exc:  # noqa: BLE001
                self._record_error(result, term, exc)
            done += 1
            if self._on_progress:
                self._on_progress(done, total)

        for term, existing in merges:
            try:
                outcome = self._runner._merge_into_existing(existing, term)
                self._record_outcome(result, outcome.action, outcome.term)
            except Exception as exc:  # noqa: BLE001
                self._record_error(result, term, exc)
            done += 1
            if self._on_progress:
                self._on_progress(done, total)

        return result

    def _enrich_concurrent(
        self, winners: list[EnrichedTerm]
    ) -> dict[int, Exception]:
        """Run `_enrich` for each winner in a thread pool; collect failures by id."""
        errors: dict[int, Exception] = {}
        if not winners:
            return errors
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {pool.submit(self._runner._enrich, t): id(t) for t in winners}
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as exc:  # noqa: BLE001
                    errors[futures[fut]] = exc
        return errors

    def _dedup_new_terms_by_label(
        self, creates: list[EnrichedTerm], result: BatchResult
    ) -> list[EnrichedTerm]:
        """Collapse new terms sharing a preferred label into one winner.

        Losers' labels + provenance are folded into the winner and the loser is
        recorded in ``skipped`` with a merge reason (mirrors the FIBO dedup).
        """
        winners: list[EnrichedTerm] = []
        by_label: dict[str, EnrichedTerm] = {}
        for term in creates:
            key = (term.preferred_label or "").casefold().strip()
            if not key:
                winners.append(term)
                continue
            winner = by_label.get(key)
            if winner is None:
                by_label[key] = term
                winners.append(term)
            else:
                self._fold_term_into(winner, term)
                result.skipped.append((
                    term,
                    f"merged into '{winner.preferred_label}' (same label, within batch)",
                ))
        return winners

    @staticmethod
    def _fold_term_into(winner: EnrichedTerm, loser: EnrichedTerm) -> None:
        seen_labels = {c.text.casefold() for c in winner.candidate_labels}
        for lbl in loser.candidate_labels:
            if lbl.text.casefold() not in seen_labels:
                winner.candidate_labels.append(
                    CandidateLabel(
                        text=lbl.text,
                        confidence=lbl.confidence * 0.8,
                        ner_label=lbl.ner_label,
                    )
                )
                seen_labels.add(lbl.text.casefold())
        seen_refs = {(p.document_ref, p.section) for p in winner.policy_context}
        for ctx in loser.policy_context:
            if (ctx.document_ref, ctx.section) not in seen_refs:
                winner.policy_context.append(ctx)
                seen_refs.add((ctx.document_ref, ctx.section))
