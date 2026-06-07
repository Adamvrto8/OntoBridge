from __future__ import annotations

from collections import Counter
from typing import Mapping

import pytest

from ontobridge.agents.mapping.strategies import TokenOverlapEncoder
from ontobridge.agents.taxonomy import (
    TaxonomyAgent,
    build_curie,
    camelcase_label,
)
from ontobridge.models import (
    CandidateLabel,
    EnrichedTerm,
    HarvestRecord,
    MatchResult,
    MatchType,
    PlacementStatus,
    SourceRef,
    SourceType,
    Tier,
)


# ---------- helpers ----------

def _term(label: str, match: MatchResult | None = None) -> EnrichedTerm:
    hr = HarvestRecord(
        text=label,
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="ui"),
        tier=Tier.UNSTRUCTURED,
    )
    t = EnrichedTerm.from_harvest(hr)
    t.candidate_labels = [CandidateLabel(text=label, confidence=0.9)]
    t.match_result = match
    return t


class SemanticStubEncoder:
    """Hand-tuned encoder that knows a few domain associations the
    TokenOverlapEncoder cannot capture (e.g. ATM ~ channel). Falls back to
    raw token overlap for everything else."""

    SEMANTIC_VECTORS: dict[str, dict[str, float]] = {
        "credit card": {"credit": 1.0, "product": 0.8, "card": 1.0, "payment": 0.6},
        "credit product": {"credit": 1.0, "product": 1.0, "lending": 0.5},
        "atm": {"channel": 1.0, "atm": 1.0, "interaction": 0.5, "physical": 0.4},
        "channel": {"channel": 1.0, "interaction": 0.7},
    }

    def __init__(self) -> None:
        self._fallback = TokenOverlapEncoder()

    def encode(self, text: str) -> Mapping[str, float]:
        key = text.casefold().strip()
        if key in self.SEMANTIC_VECTORS:
            return Counter(self.SEMANTIC_VECTORS[key])
        return self._fallback.encode(text)


# ---------- helpers: camelcase / curie ----------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("PI Customer", "PICustomer"),
        ("Credit Card", "CreditCard"),
        ("ATM", "ATM"),
        ("retail micro customer", "RetailMicroCustomer"),
        ("Retail_PI.GI", "RetailPIGI"),
        ("  spaced   label  ", "SpacedLabel"),
        ("", ""),
    ],
)
def test_camelcase_label(raw, expected):
    assert camelcase_label(raw) == expected


def test_build_curie_uses_default_bank_prefix():
    assert build_curie("PI Customer") == "bank:PICustomer"
    assert build_curie("ATM") == "bank:ATM"


def test_build_curie_accepts_custom_prefix():
    assert build_curie("PI Customer", prefix="acme") == "acme:PICustomer"


# ---------- placement via token overlap ----------

@pytest.fixture
def agent(base_ontology):
    return TaxonomyAgent(base_ontology)


def test_places_under_retail_customer_via_token_overlap(agent):
    placement = agent.evaluate(_term("Premium retail customer"))
    assert placement.status is PlacementStatus.PLACED
    assert placement.broader_concept_uri.endswith("/RetailCustomer")
    assert placement.scheme_uri.endswith("/SchemeParty")
    assert placement.domain_prefix == "bank:PremiumRetailCustomer"
    assert placement.placement_confidence > 0.5


def test_places_under_pi_loan_via_token_overlap(agent):
    placement = agent.evaluate(_term("Personal Instalment loan customer"))
    assert placement.status is PlacementStatus.PLACED
    assert placement.broader_concept_uri.endswith("/PILoan")
    assert placement.scheme_uri.endswith("/SchemeProduct")


def test_places_under_savings_account_via_token_overlap(agent):
    placement = agent.evaluate(_term("Savings deposit account"))
    assert placement.status is PlacementStatus.PLACED
    assert placement.broader_concept_uri.endswith("/SavingsAccount")


# ---------- placement via semantic stub encoder ----------

def test_credit_card_lands_under_credit_product(base_ontology):
    agent = TaxonomyAgent(base_ontology, encoder=SemanticStubEncoder())
    placement = agent.evaluate(_term("Credit Card"))
    assert placement.status is PlacementStatus.PLACED
    assert placement.broader_concept_uri.endswith("/CreditProduct")
    assert placement.scheme_uri.endswith("/SchemeProduct")
    assert placement.domain_prefix == "bank:CreditCard"


def test_atm_lands_under_channel(base_ontology):
    agent = TaxonomyAgent(base_ontology, encoder=SemanticStubEncoder())
    placement = agent.evaluate(_term("ATM"))
    assert placement.status is PlacementStatus.PLACED
    assert placement.broader_concept_uri.endswith("/Channel")
    assert placement.scheme_uri.endswith("/SchemeChannel")
    assert placement.domain_prefix == "bank:ATM"


# ---------- unresolved fallback ----------

def test_unresolved_when_no_overlap_at_all(agent):
    placement = agent.evaluate(_term("Telegraph operator licence xyz"))
    assert placement.status is PlacementStatus.UNRESOLVED
    assert placement.broader_concept_uri is None
    assert placement.scheme_uri is not None  # fallback scheme always assigned now
    assert placement.placement_confidence == 0.0
    # Even unresolved placements still propose a CURIE for the steward.
    assert placement.domain_prefix == "bank:TelegraphOperatorLicenceXyz"


def test_unresolved_keeps_best_guess_when_score_below_threshold(base_ontology):
    # 'Customer foo bar' overlaps weakly with bank:Customer (~0.58 via token overlap).
    strict = TaxonomyAgent(base_ontology, placement_threshold=0.6)
    placement = strict.evaluate(_term("Customer foo bar"))
    assert placement.status is PlacementStatus.UNRESOLVED
    # Best guess is preserved so the steward sees what the agent considered.
    assert placement.broader_concept_uri.endswith("/Customer")
    assert placement.placement_confidence < 0.6


def test_threshold_lowering_promotes_unresolved_to_placed(base_ontology):
    label = _term("Customer foo bar")
    assert TaxonomyAgent(base_ontology, placement_threshold=0.8).evaluate(label).status is PlacementStatus.UNRESOLVED
    assert TaxonomyAgent(base_ontology, placement_threshold=0.4).evaluate(label).status is PlacementStatus.PLACED


# ---------- match_result interplay ----------

def test_excludes_duplicate_target_from_parent_candidates(base_ontology):
    agent = TaxonomyAgent(base_ontology, placement_threshold=0.4)
    # New term is the same string as an existing concept; mapping declared DUPLICATE.
    match = MatchResult(
        match_type=MatchType.DUPLICATE,
        similarity=1.0,
        target_uri="http://ontobridge.dev/ontology/bank/RetailPICustomer",
    )
    placement = agent.evaluate(_term("Retail PI customer", match=match))
    # The matched concept must not be proposed as its own parent.
    assert placement.broader_concept_uri != "http://ontobridge.dev/ontology/bank/RetailPICustomer"


def test_excludes_fuzzy_target_from_parent_candidates(base_ontology):
    agent = TaxonomyAgent(base_ontology, placement_threshold=0.4)
    match = MatchResult(
        match_type=MatchType.FUZZY,
        similarity=0.97,
        target_uri="http://ontobridge.dev/ontology/bank/RetailPICustomer",
    )
    placement = agent.evaluate(_term("Retail PI customer profile", match=match))
    assert placement.broader_concept_uri != "http://ontobridge.dev/ontology/bank/RetailPICustomer"


def test_no_exclusion_for_new_match(agent):
    # NEW match means no near-duplicate exists; no exclusion should occur.
    match = MatchResult(match_type=MatchType.NEW, similarity=0.0)
    placement = agent.evaluate(_term("Premium retail customer", match=match))
    assert placement.status is PlacementStatus.PLACED
    assert placement.broader_concept_uri.endswith("/RetailCustomer")


# ---------- sibling conflicts ----------

def test_sibling_conflict_detected_when_label_matches_a_sibling(base_ontology):
    agent = TaxonomyAgent(base_ontology, placement_threshold=0.4)
    match = MatchResult(
        match_type=MatchType.FUZZY,
        similarity=0.97,
        target_uri="http://ontobridge.dev/ontology/bank/RetailPICustomer",
    )
    placement = agent.evaluate(_term("Retail PI customer group", match=match))
    assert placement.broader_concept_uri.endswith("/RetailCustomer")
    sibling_uris = {sc.sibling_uri for sc in placement.sibling_conflicts}
    assert any(uri.endswith("/RetailPICustomer") for uri in sibling_uris)


def test_sibling_conflict_threshold_can_be_raised(base_ontology):
    match = MatchResult(
        match_type=MatchType.FUZZY,
        similarity=0.97,
        target_uri="http://ontobridge.dev/ontology/bank/RetailPICustomer",
    )
    strict_agent = TaxonomyAgent(
        base_ontology,
        placement_threshold=0.4,
        sibling_conflict_threshold=0.99,
    )
    placement = strict_agent.evaluate(_term("Retail PI customers", match=match))
    assert placement.sibling_conflicts == []


def test_no_sibling_conflicts_for_unrelated_siblings(agent):
    placement = agent.evaluate(_term("Premium retail customer"))
    # Siblings of RetailCustomer are RetailPICustomer and RetailMicroCustomer;
    # 'Premium retail customer' shouldn't fuzzy-match either at >=0.80.
    assert placement.sibling_conflicts == []


def test_unresolved_placement_has_no_sibling_conflicts(agent):
    placement = agent.evaluate(_term("Telegraph operator licence xyz"))
    assert placement.status is PlacementStatus.UNRESOLVED
    assert placement.sibling_conflicts == []


# ---------- agent contract ----------

def test_apply_writes_placement_into_term(agent):
    term = _term("Premium retail customer")
    returned = agent.apply(term)
    assert returned is term
    assert term.taxonomy_placement is not None
    assert term.taxonomy_placement.status is PlacementStatus.PLACED


def test_evaluate_raises_when_no_candidate_labels(agent):
    hr = HarvestRecord(
        text="x",
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="ui"),
        tier=Tier.UNSTRUCTURED,
    )
    t = EnrichedTerm.from_harvest(hr)
    with pytest.raises(ValueError, match="candidate_labels"):
        agent.evaluate(t)


def test_uses_highest_confidence_candidate_label(agent):
    hr = HarvestRecord(
        text="x",
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="ui"),
        tier=Tier.UNSTRUCTURED,
    )
    t = EnrichedTerm.from_harvest(hr)
    t.candidate_labels = [
        CandidateLabel(text="Junk noise tokens", confidence=0.2),
        CandidateLabel(text="Premium retail customer", confidence=0.95),
    ]
    placement = agent.evaluate(t)
    assert placement.broader_concept_uri.endswith("/RetailCustomer")


def test_constructor_validates_thresholds(base_ontology):
    with pytest.raises(ValueError, match="placement_threshold"):
        TaxonomyAgent(base_ontology, placement_threshold=1.5)
    with pytest.raises(ValueError, match="sibling_conflict_threshold"):
        TaxonomyAgent(base_ontology, sibling_conflict_threshold=-0.1)


def test_pluggable_encoder_changes_outcome(base_ontology):
    """Same label, different encoders → different parents (sanity check the
    Encoder protocol is wired through the agent)."""
    overlap_agent = TaxonomyAgent(base_ontology)
    semantic_agent = TaxonomyAgent(base_ontology, encoder=SemanticStubEncoder())
    label = _term("Credit Card")
    overlap_placement = overlap_agent.evaluate(label)
    semantic_placement = semantic_agent.evaluate(label)
    # Token-overlap can't reach 0.5 cleanly on 'Credit Card' but the semantic
    # encoder does — placement status should flip.
    assert overlap_placement.status is PlacementStatus.UNRESOLVED
    assert semantic_placement.status is PlacementStatus.PLACED
