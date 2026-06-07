"""Regression tests for LLM-based synonym deduplication in batch pipeline."""
import pytest
from ontobridge.batch import BatchPipelineRunner, BatchResult
from ontobridge.models import CandidateLabel, EnrichedTerm, SourceRef, SourceType, Tier, HarvestRecord
from ontobridge.publisher import InMemoryPublisher


def _harvest_record(text: str) -> HarvestRecord:
    return HarvestRecord(
        text=text,
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="test"),
        tier=Tier.UNSTRUCTURED,
    )


def test_no_dedup_without_llm_backend(base_ontology):
    """Without LLM backend, close-but-not-identical terms stay separate.
    
    This is the expected behavior now — we don't use aggressive fuzzy matching
    because LLM does it better. Fuzzy dedup was removed.
    """
    publisher = InMemoryPublisher()
    runner = BatchPipelineRunner(ontology=base_ontology, publisher=publisher)

    term1 = EnrichedTerm.from_harvest(_harvest_record("LTV ratio definition"))
    term1.candidate_labels = [CandidateLabel(text="LTV ratio", confidence=0.95)]
    term1.definition = "The loan amount divided by property value as a percentage."

    term2 = EnrichedTerm.from_harvest(_harvest_record("Loan-to-Value Ratio definition"))
    term2.candidate_labels = [CandidateLabel(text="Loan-to-Value Ratio", confidence=0.95)]
    term2.definition = "The percentage of property value financed by the lender."

    result = runner.run_terms([term1, term2])

    # Without LLM or FIBO match, both should be published as separate terms
    assert len(result.published) == 2, "No dedup without LLM backend"
    assert len(result.skipped) == 0


def test_exact_duplicate_still_caught_by_fibo(base_ontology):
    """If both terms match the same FIBO URI, they are merged by FIBO dedup."""
    publisher = InMemoryPublisher()
    runner = BatchPipelineRunner(ontology=base_ontology, publisher=publisher)

    # Simulate FIBO matching — set fibo_match on both
    from ontobridge.models.fibo import FIBOMatch
    fibo_match = FIBOMatch(
        uri="https://spec.edmcouncil.org/fibo/ontology/LOAN/LoansGeneral/Loans/LoanToValueRatio",
        match_type="exact",
    )

    term1 = EnrichedTerm.from_harvest(_harvest_record("LTV ratio"))
    term1.candidate_labels = [CandidateLabel(text="LTV ratio", confidence=0.95)]
    term1.definition = "Loan to value ratio."
    term1.fibo_match = fibo_match

    term2 = EnrichedTerm.from_harvest(_harvest_record("Loan-to-Value Ratio"))
    term2.candidate_labels = [CandidateLabel(text="Loan-to-Value Ratio", confidence=0.95)]
    term2.definition = "Loan to value ratio full name."
    term2.fibo_match = fibo_match

    result = runner.run_terms([term1, term2])

    # Should merge by FIBO
    assert len(result.published) == 1, "Should merge terms with same FIBO URI"
    assert len(result.skipped) == 1, "One term merged into winner"
    assert "merged" in result.skipped[0][1].lower()


def test_dissimilar_terms_not_merged(base_ontology):
    """Completely dissimilar terms are never merged."""
    publisher = InMemoryPublisher()
    runner = BatchPipelineRunner(ontology=base_ontology, publisher=publisher)

    term1 = EnrichedTerm.from_harvest(_harvest_record("LTV"))
    term1.candidate_labels = [CandidateLabel(text="Loan-to-Value Ratio", confidence=0.95)]
    term1.definition = "A measure of loan to property value."

    term2 = EnrichedTerm.from_harvest(_harvest_record("Interest Rate"))
    term2.candidate_labels = [CandidateLabel(text="Interest Rate", confidence=0.95)]
    term2.definition = "The percentage charged on borrowed money."

    result = runner.run_terms([term1, term2])

    assert len(result.published) == 2, "Should publish 2 dissimilar terms"
    assert len(result.skipped) == 0, "No merges should occur"

