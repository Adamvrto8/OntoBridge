from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.models import (
    CandidateLabel,
    EnrichedTerm,
    HarvestRecord,
    LifecycleStatus,
    PolicyContext,
    SourceRef,
    SourceType,
    Tier,
)
from ontobridge.pipeline import PipelineRunner
from ontobridge.publisher import InMemoryPublisher


@dataclass(frozen=True)
class SampleTermSpec:
    label: str
    definition: str
    policy_document: str
    policy_section: str
    approved_by: str | None = None
    transition_to_after_publish: LifecycleStatus | None = None


def sample_term_specs() -> list[SampleTermSpec]:
    return [
        SampleTermSpec(
            label="Premium retail customer",
            definition=(
                "A retail customer who holds premium credit products with the bank "
                "and uses concierge channels for high-touch service."
            ),
            policy_document="CreditPolicy_v3.pdf",
            policy_section="4.2",
            approved_by="alice.steward",
        ),
        SampleTermSpec(
            label="Joint account holder",
            definition=(
                "A retail customer who holds an account jointly with one or more "
                "other parties and submits shared signing instructions."
            ),
            policy_document="DepositsPolicy_v2.pdf",
            policy_section="3.1",
        ),
        SampleTermSpec(
            label="Loan repayment schedule",
            definition=(
                "A document that governs the periodic repayment instalments a "
                "customer submits against an outstanding loan obligation."
            ),
            policy_document="CreditPolicy_v3.pdf",
            policy_section="5.4",
        ),
        SampleTermSpec(
            label="KYC verification process",
            definition=(
                "A verification process that evaluates customer identity and "
                "produces a regulatory compliance record before onboarding."
            ),
            policy_document="OnboardingPolicy_v2.pdf",
            policy_section="1.2",
            approved_by="bob.steward",
        ),
        SampleTermSpec(
            label="Retail customer",  # exact duplicate of an existing prefLabel
            definition=(
                "A natural person who holds retail products at the bank for "
                "personal use across all channels."
            ),
            policy_document="CreditPolicy_v3.pdf",
            policy_section="1.1",
        ),
        SampleTermSpec(
            label="ATM withdrawal",
            definition=(
                "A cash withdrawal operation that uses an ATM channel and "
                "produces a transaction record on the customer account."
            ),
            policy_document="ChannelsPolicy_v1.pdf",
            policy_section="2.3",
            transition_to_after_publish=LifecycleStatus.DRAFT,
        ),
    ]


def build_enriched_term(spec: SampleTermSpec) -> EnrichedTerm:
    harvest = HarvestRecord(
        text=spec.definition,
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(
            source_system="policy_repo",
            document_id=spec.policy_document,
            section=spec.policy_section,
        ),
        tier=Tier.DOCUMENT,
    )
    term = EnrichedTerm.from_harvest(harvest)
    term.candidate_labels = [CandidateLabel(text=spec.label, confidence=0.95)]
    term.definition = spec.definition
    term.policy_context = [
        PolicyContext(
            paragraph=spec.definition,
            document_ref=spec.policy_document,
            section=spec.policy_section,
        ),
    ]
    return term


def build_sample_publisher(
    ontology: OntologyIndex,
    specs: list[SampleTermSpec] | None = None,
) -> InMemoryPublisher:
    """Run a curated set of terms through the PipelineRunner to populate an
    InMemoryPublisher with a mix of lifecycle states for the dashboard."""
    pub = InMemoryPublisher()
    runner = PipelineRunner(ontology, pub)
    specs = specs if specs is not None else sample_term_specs()

    for spec in specs:
        term = build_enriched_term(spec)
        try:
            published = runner.run(term, approved_by=spec.approved_by)
        except ValueError:
            # If the writer rejects the URI (collision), skip that sample.
            continue
        if spec.transition_to_after_publish is not None:
            try:
                pub.transition_status(
                    published.term_uri, spec.transition_to_after_publish
                )
            except ValueError:
                pass

    return pub


def load_ontology(path: Path | str) -> OntologyIndex:
    return OntologyIndex.from_file(path)
