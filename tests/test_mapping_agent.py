from __future__ import annotations

import pytest

from ontobridge.agents.mapping import (
    GlossaryEntry,
    MappingAgent,
    from_entries,
    from_ontology,
    from_publisher,
)
from ontobridge.models import (
    CandidateLabel,
    EnrichedTerm,
    HarvestRecord,
    LifecycleStatus,
    MatchType,
    PublishedTerm,
    SourceRef,
    SourceType,
    Tier,
)
from ontobridge.publisher import InMemoryPublisher


def _term(label: str, confidence: float = 0.9) -> EnrichedTerm:
    hr = HarvestRecord(
        text=label,
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="ui"),
        tier=Tier.UNSTRUCTURED,
    )
    t = EnrichedTerm.from_harvest(hr)
    t.candidate_labels = [CandidateLabel(text=label, confidence=confidence)]
    return t


@pytest.fixture
def agent(base_ontology):
    return MappingAgent(from_ontology(base_ontology))


# ---- DUPLICATE ----

def test_exact_pref_label_returns_duplicate(agent):
    result = agent.evaluate(_term("Retail customer"))
    assert result.match_type is MatchType.DUPLICATE
    assert result.similarity == 1.0
    assert result.target_uri.endswith("/RetailCustomer")
    assert result.alternative_matches == []


def test_exact_alt_label_returns_duplicate(agent):
    # "Individual customer" is altLabel of bank:RetailCustomer
    result = agent.evaluate(_term("Individual customer"))
    assert result.match_type is MatchType.DUPLICATE
    assert result.target_uri.endswith("/RetailCustomer")


def test_case_insensitive_exact_match(agent):
    assert agent.evaluate(_term("retail customer")).match_type is MatchType.DUPLICATE


# ---- FUZZY ----

def test_fuzzy_match_above_threshold(agent):
    result = agent.evaluate(_term("Retail custmer"))
    assert result.match_type is MatchType.FUZZY
    assert result.target_uri.endswith("/RetailCustomer")
    assert 0.75 <= result.similarity < 1.0


def test_fuzzy_match_provides_ranked_alternatives(agent):
    result = agent.evaluate(_term("Retail custmer"))
    assert result.alternative_matches  # token-overlap should surface other "customer" terms
    scores = [s for _, s in result.alternative_matches]
    assert scores == sorted(scores, reverse=True)


def test_lower_threshold_widens_fuzzy(base_ontology):
    # "Mob banking app" is ~0.76 similar to "Mobile app" — straddles 0.80 / 0.60.
    strict = MappingAgent(from_ontology(base_ontology), fuzzy_threshold=0.80)
    lax = MappingAgent(from_ontology(base_ontology), fuzzy_threshold=0.60)
    assert strict.evaluate(_term("Mob banking app")).match_type is MatchType.NEW
    assert lax.evaluate(_term("Mob banking app")).match_type is MatchType.FUZZY


# ---- NEW ----

def test_unknown_label_returns_new(agent):
    result = agent.evaluate(_term("Telegraph operator licence"))
    assert result.match_type is MatchType.NEW
    assert result.target_uri is None
    assert result.similarity == 0.0


def test_new_match_still_lists_alternatives_when_token_overlap_exists(agent):
    # "Loan" shares the token with bank:LoanApplication / bank:PILoan / bank:MicroLoan
    # via the embedding (token-overlap) strategy, even with no fuzzy hit.
    result = agent.evaluate(_term("Loan"))
    assert result.match_type is MatchType.NEW
    assert any("Loan" in uri for uri, _ in result.alternative_matches)


# ---- apply() ----

def test_apply_writes_match_result_into_term(agent):
    term = _term("Retail customer")
    returned = agent.apply(term)
    assert returned is term
    assert term.match_result is not None
    assert term.match_result.match_type is MatchType.DUPLICATE


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
    """When the term has multiple candidate labels, mapping uses the top one."""
    hr = HarvestRecord(
        text="x",
        source_type=SourceType.USER_INPUT,
        source_ref=SourceRef(source_system="ui"),
        tier=Tier.UNSTRUCTURED,
    )
    t = EnrichedTerm.from_harvest(hr)
    t.candidate_labels = [
        CandidateLabel(text="Junk noise", confidence=0.2),
        CandidateLabel(text="Retail customer", confidence=0.95),
    ]
    result = agent.evaluate(t)
    assert result.match_type is MatchType.DUPLICATE


# ---- glossary integration ----

def test_agent_works_against_publisher_glossary():
    pub = InMemoryPublisher()
    enriched = EnrichedTerm.from_harvest(
        HarvestRecord(
            text="Retail customer",
            source_type=SourceType.USER_INPUT,
            source_ref=SourceRef(source_system="ui"),
            tier=Tier.UNSTRUCTURED,
        )
    )
    enriched.candidate_labels = [CandidateLabel(text="Retail customer", confidence=0.95)]
    pub.create_term(
        PublishedTerm(
            enriched_term=enriched,
            term_uri="bank:RetailCustomer",
            lifecycle_status=LifecycleStatus.PUBLISHED,
            approved_by="alice",
        )
    )
    agent = MappingAgent(from_publisher(pub))
    assert agent.evaluate(_term("retail customer")).target_uri == "bank:RetailCustomer"


def test_agent_works_against_in_memory_glossary():
    g = from_entries([
        GlossaryEntry(uri="ex:Foo", pref_label="Foo bar"),
        GlossaryEntry(uri="ex:Baz", pref_label="Baz qux"),
    ])
    agent = MappingAgent(g, fuzzy_threshold=0.7)
    result = agent.evaluate(_term("Foo barr"))
    assert result.match_type is MatchType.FUZZY
    assert result.target_uri == "ex:Foo"


def test_match_result_validates_into_enrichedterm(agent):
    """MatchResult must satisfy EnrichedTerm's validation when assigned via apply()."""
    term = _term("Retail customer")
    agent.apply(term)
    assert term.match_result is not None
    # MatchResult.__post_init__ enforces target_uri for DUPLICATE — this assignment must
    # have produced a valid result.
    assert term.match_result.target_uri is not None
