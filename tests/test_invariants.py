"""
Invariant tests for the OntoBridge pipeline agents.

These tests verify structural constraints that must ALWAYS hold on agent
outputs — regardless of the specific input.  They are NOT testing whether
the semantic result is *good*, only that it is internally *consistent*.

Groups:
  1. Model-level invariants   — pure unit tests, no agent instantiation.
  2. GovernanceAgent           — rule count, blocking-flag consistency.
  3. TaxonomyAgent             — placed URIs exist in the ontology.
  4. MappingAgent              — similarity range, DUPLICATE always has target_uri.
  5. RelationsAgent            — RESOLVED always has both predicate URIs.
"""

from __future__ import annotations

import pytest

from ontobridge.agents.governance import GovernanceAgent
from ontobridge.agents.governance.models import Candidate
from ontobridge.agents.governance.rules import default_rules
from ontobridge.agents.mapping import MappingAgent, from_ontology
from ontobridge.agents.relations import RelationsAgent
from ontobridge.agents.taxonomy import TaxonomyAgent
from ontobridge.models.enrichment import (
    CandidateLabel,
    EnrichedTerm,
    MatchResult,
    SemanticRelation,
    TaxonomyPlacement,
)
from ontobridge.models.enums import (
    MatchType,
    PlacementStatus,
    RelationStatus,
)
from ontobridge.models.fibo import FIBOMatch
from ontobridge.models.source import HarvestRecord, SourceRef, SourceType, Tier


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _harvest(text: str = "A financial term used in banking.") -> HarvestRecord:
    return HarvestRecord(
        text=text,
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="ui"),
        tier=Tier.UNSTRUCTURED,
    )


def _term(label: str, definition: str | None = None) -> EnrichedTerm:
    t = EnrichedTerm.from_harvest(_harvest(definition or "A financial term."))
    t.candidate_labels = [CandidateLabel(text=label, confidence=0.9)]
    if definition:
        t.definition = definition
    return t


# ─── 1. Model-level invariants ────────────────────────────────────────────────


class TestSemanticRelationModel:
    """SemanticRelation: RESOLVED requires both predicate URIs; confidence in range."""

    def test_resolved_requires_predicate_uri(self):
        with pytest.raises(ValueError, match="predicate_uri"):
            SemanticRelation(
                subject_uri="http://example.com/A",
                predicate_uri=None,
                object_label="B",
                inverse_predicate_uri="http://example.com/rel/inv",
                verb="uses",
                status=RelationStatus.RESOLVED,
            )

    def test_resolved_requires_inverse_predicate_uri(self):
        with pytest.raises(ValueError, match="inverse_predicate_uri"):
            SemanticRelation(
                subject_uri="http://example.com/A",
                predicate_uri="http://example.com/rel/uses",
                object_label="B",
                inverse_predicate_uri=None,
                verb="uses",
                status=RelationStatus.RESOLVED,
            )

    def test_proposed_allows_null_predicate_uris(self):
        rel = SemanticRelation(
            subject_uri="http://example.com/A",
            predicate_uri=None,
            object_label="B",
            inverse_predicate_uri=None,
            verb="influences",
            status=RelationStatus.PROPOSED,
        )
        assert rel.predicate_uri is None
        assert rel.inverse_predicate_uri is None

    def test_unresolved_verb_allows_null_predicate_uris(self):
        rel = SemanticRelation(
            subject_uri="http://example.com/A",
            predicate_uri=None,
            object_label="B",
            inverse_predicate_uri=None,
            verb="xyzzy",
            status=RelationStatus.UNRESOLVED_VERB,
        )
        assert rel.status == RelationStatus.UNRESOLVED_VERB

    @pytest.mark.parametrize("bad_confidence", [-0.01, 1.01, -1.0, 2.0])
    def test_confidence_out_of_range_rejected(self, bad_confidence):
        with pytest.raises(ValueError, match="confidence"):
            SemanticRelation(
                subject_uri="http://example.com/A",
                predicate_uri=None,
                object_label="B",
                inverse_predicate_uri=None,
                verb="uses",
                status=RelationStatus.PROPOSED,
                confidence=bad_confidence,
            )

    def test_empty_subject_uri_rejected(self):
        with pytest.raises(ValueError):
            SemanticRelation(
                subject_uri="",
                predicate_uri=None,
                object_label="B",
                inverse_predicate_uri=None,
                verb="uses",
            )

    def test_empty_object_label_rejected(self):
        with pytest.raises(ValueError):
            SemanticRelation(
                subject_uri="http://example.com/A",
                predicate_uri=None,
                object_label="",
                inverse_predicate_uri=None,
                verb="uses",
            )


class TestTaxonomyPlacementModel:
    """TaxonomyPlacement: PLACED requires both URIs; UNRESOLVED allows None."""

    def test_placed_requires_broader_concept_uri(self):
        with pytest.raises(ValueError, match="broader_concept_uri"):
            TaxonomyPlacement(
                broader_concept_uri=None,
                scheme_uri="http://ontobridge.dev/ontology/bank/Product",
                status=PlacementStatus.PLACED,
            )

    def test_placed_requires_scheme_uri(self):
        with pytest.raises(ValueError, match="scheme_uri"):
            TaxonomyPlacement(
                broader_concept_uri="http://ontobridge.dev/ontology/bank/Loan",
                scheme_uri=None,
                status=PlacementStatus.PLACED,
            )

    def test_unresolved_allows_null_uris(self):
        tp = TaxonomyPlacement(
            broader_concept_uri=None,
            scheme_uri=None,
            status=PlacementStatus.UNRESOLVED,
        )
        assert tp.broader_concept_uri is None
        assert tp.scheme_uri is None

    @pytest.mark.parametrize("bad", [-0.01, 1.01])
    def test_placement_confidence_out_of_range_rejected(self, bad):
        with pytest.raises(ValueError, match="placement_confidence"):
            TaxonomyPlacement(
                broader_concept_uri="http://ontobridge.dev/ontology/bank/Loan",
                scheme_uri="http://ontobridge.dev/ontology/bank/Product",
                placement_confidence=bad,
            )


class TestMatchResultModel:
    """MatchResult: DUPLICATE requires target_uri; similarity in range."""

    def test_duplicate_without_target_uri_rejected(self):
        with pytest.raises(ValueError, match="target_uri"):
            MatchResult(
                match_type=MatchType.DUPLICATE,
                similarity=0.95,
                target_uri=None,
            )

    def test_new_match_has_no_target_uri(self):
        mr = MatchResult(match_type=MatchType.NEW, similarity=0.0)
        assert mr.target_uri is None

    @pytest.mark.parametrize("bad", [-0.01, 1.01])
    def test_similarity_out_of_range_rejected(self, bad):
        with pytest.raises(ValueError, match="similarity"):
            MatchResult(match_type=MatchType.NEW, similarity=bad)


class TestFIBOMatchModel:
    """FIBOMatch: empty URI rejected; match_type must be exact/close/broad."""

    def test_empty_uri_rejected(self):
        with pytest.raises(ValueError, match="uri"):
            FIBOMatch(uri="", match_type="exact")

    def test_invalid_match_type_rejected(self):
        with pytest.raises(ValueError, match="match_type"):
            FIBOMatch(uri="https://spec.edmcouncil.org/fibo/X", match_type="unknown")

    @pytest.mark.parametrize("valid_type", ["exact", "close", "broad"])
    def test_valid_match_types_accepted(self, valid_type):
        fm = FIBOMatch(uri="https://spec.edmcouncil.org/fibo/X", match_type=valid_type)
        assert fm.match_type == valid_type


class TestCandidateLabelModel:
    """CandidateLabel: empty text rejected; confidence in range."""

    def test_empty_text_rejected(self):
        with pytest.raises(ValueError, match="text"):
            CandidateLabel(text="", confidence=0.9)

    def test_whitespace_only_text_rejected(self):
        with pytest.raises(ValueError, match="text"):
            CandidateLabel(text="   ", confidence=0.9)

    @pytest.mark.parametrize("bad", [-0.01, 1.01])
    def test_confidence_out_of_range_rejected(self, bad):
        with pytest.raises(ValueError, match="confidence"):
            CandidateLabel(text="Mortgage", confidence=bad)


# ─── 2. GovernanceAgent invariants ────────────────────────────────────────────


class TestGovernanceAgentInvariants:
    """GovernanceAgent must evaluate all 14 rules and keep blocking_flags consistent."""

    @pytest.fixture
    def gov(self, base_ontology):
        return GovernanceAgent(ontology=base_ontology, rules=default_rules())

    def _candidate(self, label="Mortgage Loan", definition="A loan secured by real property."):
        return Candidate(preferred_label=label, definition=definition)

    def test_always_produces_14_findings(self, gov):
        result = gov.evaluate(self._candidate())
        assert len(result.findings) == 14

    def test_finding_rule_ids_are_1_to_14(self, gov):
        result = gov.evaluate(self._candidate())
        ids = {f.rule_id for f in result.findings}
        assert ids == set(range(1, 15))

    def test_by_rule_returns_non_none_for_all_ids(self, gov):
        result = gov.evaluate(self._candidate())
        for rule_id in range(1, 15):
            assert result.by_rule(rule_id) is not None

    def test_recommended_action_is_valid_enum_value(self, gov):
        result = gov.evaluate(self._candidate())
        assert result.recommended_action in {"publish", "review", "block", "draft"}

    def test_blocking_flags_implies_block_action(self, gov):
        result = gov.evaluate(self._candidate())
        if result.blocking_flags:
            assert result.recommended_action == "block"

    def test_block_action_implies_blocking_flags(self, gov):
        result = gov.evaluate(self._candidate())
        if result.recommended_action == "block":
            assert len(result.blocking_flags) > 0

    def test_triggered_is_subset_of_all_findings(self, gov):
        result = gov.evaluate(self._candidate())
        triggered_ids = {f.rule_id for f in result.triggered}
        all_ids = {f.rule_id for f in result.findings}
        assert triggered_ids.issubset(all_ids)

    def test_term_without_definition_is_not_published(self, gov):
        result = gov.evaluate(Candidate(preferred_label="UndefinedTerm"))
        assert result.recommended_action in {"block", "draft", "review"}

    @pytest.mark.parametrize("label,definition", [
        ("Mortgage Loan", "A loan secured by property."),
        ("Credit Risk", "The risk that a borrower defaults on an obligation."),
        ("Collateral", "An asset pledged to secure a loan."),
        ("Interest Rate", "The percentage charged on borrowed capital."),
        ("LTV", "Loan-to-value ratio, expressed as a percentage."),
    ])
    def test_14_findings_across_diverse_inputs(self, gov, label, definition):
        result = gov.evaluate(self._candidate(label, definition))
        assert len(result.findings) == 14


# ─── 3. TaxonomyAgent invariants ──────────────────────────────────────────────


class TestTaxonomyAgentInvariants:
    """TaxonomyAgent: PLACED output references URIs that actually exist in the ontology."""

    @pytest.fixture
    def tax(self, base_ontology):
        return TaxonomyAgent(base_ontology)

    @pytest.fixture
    def known_uris(self, base_ontology):
        return {c.uri for c in base_ontology.concepts}

    @pytest.mark.parametrize("label,definition", [
        ("Mortgage Loan", "A loan secured by real estate property."),
        ("Credit Risk", "The risk that a borrower may default on a loan."),
        ("Interest Rate", "The percentage charged on a loan principal."),
        ("Customer", "A person or entity that holds a bank account."),
        ("Payment", "A transfer of funds to settle a financial obligation."),
    ])
    def test_placed_broader_concept_uri_exists_in_ontology(
        self, tax, known_uris, label, definition
    ):
        placement = tax.evaluate(_term(label, definition))
        if placement.status == PlacementStatus.PLACED:
            assert placement.broader_concept_uri in known_uris, (
                f"'{label}' placed under unknown URI: {placement.broader_concept_uri}"
            )

    @pytest.mark.parametrize("label,definition", [
        ("Mortgage Loan", "A loan secured by real estate property."),
        ("Credit Risk", "The risk that a borrower may default on a loan."),
    ])
    def test_placement_confidence_in_range(self, tax, label, definition):
        placement = tax.evaluate(_term(label, definition))
        assert 0.0 <= placement.placement_confidence <= 1.0

    def test_apply_mutates_term_in_place_and_returns_it(self, tax):
        term = _term("Mortgage Loan", "A loan secured by real property.")
        returned = tax.apply(term)
        assert returned is term
        assert term.taxonomy_placement is not None

    def test_unresolved_placement_has_null_broader_concept_uri(self, tax):
        # UNRESOLVED means no specific parent was found; scheme_uri may still be
        # populated with a default, but broader_concept_uri must be None.
        term = _term("XYZ123Gobbledygook", "Completely nonsense input that matches nothing.")
        placement = tax.evaluate(term)
        if placement.status == PlacementStatus.UNRESOLVED:
            assert placement.broader_concept_uri is None

    def test_placed_scheme_uri_is_non_empty(self, tax):
        term = _term("Mortgage Loan", "A loan secured by real estate property.")
        placement = tax.evaluate(term)
        if placement.status == PlacementStatus.PLACED:
            assert placement.scheme_uri and placement.scheme_uri.strip()


# ─── 4. MappingAgent invariants ───────────────────────────────────────────────


class TestMappingAgentInvariants:
    """MappingAgent: similarity always in [0,1]; DUPLICATE always carries target_uri."""

    @pytest.fixture
    def mapping(self, base_ontology):
        return MappingAgent(glossary=from_ontology(base_ontology))

    @pytest.mark.parametrize("label", [
        "Mortgage Loan",
        "Credit Risk",
        "Interest Rate",
        "CompletelyUnknownBankingTerm42",
        "Loan",
    ])
    def test_similarity_always_in_range(self, mapping, label):
        result = mapping.evaluate(_term(label))
        assert 0.0 <= result.similarity <= 1.0, (
            f"Similarity out of range for '{label}': {result.similarity}"
        )

    @pytest.mark.parametrize("label", [
        "Mortgage Loan",
        "Credit Risk",
        "Loan",
        "Customer",
        "Payment",
    ])
    def test_duplicate_result_always_has_target_uri(self, mapping, label):
        result = mapping.evaluate(_term(label))
        if result.match_type == MatchType.DUPLICATE:
            assert result.target_uri is not None
            assert result.target_uri.strip() != ""

    def test_new_result_has_no_target_uri(self, mapping):
        result = mapping.evaluate(_term("CompletelyUnknownBankingTerm42"))
        if result.match_type == MatchType.NEW:
            assert result.target_uri is None

    def test_match_type_is_valid_enum(self, mapping):
        result = mapping.evaluate(_term("Mortgage Loan"))
        assert result.match_type in {MatchType.DUPLICATE, MatchType.FUZZY, MatchType.NEW}


# ─── 5. RelationsAgent invariants ─────────────────────────────────────────────


class TestRelationsAgentInvariants:
    """RelationsAgent: RESOLVED always has both predicate URIs; confidence in range."""

    @pytest.fixture
    def rel(self, base_ontology):
        return RelationsAgent(ontology=base_ontology)

    @pytest.mark.parametrize("label,definition", [
        (
            "Mortgage Loan",
            "A mortgage loan is secured by real property. "
            "The borrower uses collateral to guarantee repayment to the lender.",
        ),
        (
            "Credit Risk",
            "Credit risk arises when a borrower fails to repay a loan. "
            "It affects the lender and influences the interest rate.",
        ),
        (
            "Interest Rate",
            "An interest rate is set by the central bank. "
            "It governs borrowing costs and affects mortgage payments.",
        ),
    ])
    def test_resolved_relations_have_both_predicate_uris(self, rel, label, definition):
        term = _term(label, definition)
        rel.apply(term)
        for r in term.relations:
            if r.status == RelationStatus.RESOLVED:
                assert r.predicate_uri is not None, (
                    f"RESOLVED '{r.verb} → {r.object_label}' missing predicate_uri"
                )
                assert r.inverse_predicate_uri is not None, (
                    f"RESOLVED '{r.verb} → {r.object_label}' missing inverse_predicate_uri"
                )

    @pytest.mark.parametrize("label,definition", [
        ("Mortgage Loan", "A loan secured by real property. The borrower repays the lender."),
        ("Collateral", "An asset pledged to secure a loan against default risk."),
    ])
    def test_confidence_always_in_range(self, rel, label, definition):
        term = _term(label, definition)
        rel.apply(term)
        for r in term.relations:
            assert 0.0 <= r.confidence <= 1.0, (
                f"Confidence out of range: {r.confidence} for '{r.verb} → {r.object_label}'"
            )

    @pytest.mark.parametrize("label,definition", [
        ("Interest Rate", "Interest rate is set by the bank and affects borrowing costs."),
    ])
    def test_source_values_are_valid(self, rel, label, definition):
        term = _term(label, definition)
        rel.apply(term)
        valid_sources = {"fibo", "llm", "svo", None}
        for r in term.relations:
            assert r.source in valid_sources, (
                f"Invalid source: {r.source!r} for '{r.verb} → {r.object_label}'"
            )

    def test_apply_returns_same_term_object(self, rel):
        term = _term("Loan", "A loan is issued by a bank to a borrower.")
        returned = rel.apply(term)
        assert returned is term

    def test_unresolved_verb_relations_have_null_predicate_uris(self, rel):
        term = _term("Loan", "A loan is xyzzy by a bank to a borrower.")
        rel.apply(term)
        for r in term.relations:
            if r.status == RelationStatus.UNRESOLVED_VERB:
                assert r.predicate_uri is None
                assert r.inverse_predicate_uri is None
