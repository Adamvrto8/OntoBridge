from __future__ import annotations

import pytest

from ontobridge.agents.mapping import (
    EmbeddingSimilarityStrategy,
    ExactMatchStrategy,
    FuzzyStringStrategy,
    GlossaryEntry,
    TokenOverlapEncoder,
    from_entries,
    from_ontology,
)


@pytest.fixture
def glossary(base_ontology):
    return from_ontology(base_ontology)


# ---- Exact ----

def test_exact_matches_pref_label(glossary):
    hits = ExactMatchStrategy().match("Retail customer", glossary)
    assert len(hits) == 1
    assert hits[0].label_kind == "prefLabel"
    assert hits[0].score == 1.0
    assert hits[0].target_uri.endswith("/RetailCustomer")


def test_exact_is_case_insensitive(glossary):
    hits = ExactMatchStrategy().match("RETAIL CUSTOMER", glossary)
    assert len(hits) == 1


def test_exact_matches_alt_label(glossary):
    # "Individual customer" is the altLabel of bank:RetailCustomer
    hits = ExactMatchStrategy().match("Individual customer", glossary)
    assert len(hits) == 1
    assert hits[0].label_kind == "altLabel"
    assert hits[0].target_uri.endswith("/RetailCustomer")


def test_exact_returns_empty_for_unknown_label(glossary):
    assert ExactMatchStrategy().match("Telegraph operator licence", glossary) == []


# ---- Fuzzy ----

def test_fuzzy_picks_up_typo(glossary):
    hits = FuzzyStringStrategy(threshold=0.75).match("Retail custmer", glossary)
    assert hits, "expected at least one fuzzy hit"
    top = hits[0]
    assert top.target_uri.endswith("/RetailCustomer")
    assert 0.75 <= top.score < 1.0


def test_fuzzy_excludes_score_one_matches(glossary):
    # An exact match should NOT appear in fuzzy results.
    hits = FuzzyStringStrategy(threshold=0.75).match("Retail customer", glossary)
    assert all(h.score < 1.0 for h in hits)


def test_fuzzy_returns_sorted_descending(glossary):
    hits = FuzzyStringStrategy(threshold=0.6).match("Retail customer", glossary)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_fuzzy_below_threshold_returns_empty(glossary):
    hits = FuzzyStringStrategy(threshold=0.99).match("Retail custmer", glossary)
    assert hits == []


def test_fuzzy_rejects_invalid_threshold():
    with pytest.raises(ValueError):
        FuzzyStringStrategy(threshold=1.5)


def test_fuzzy_one_match_per_target(glossary):
    # Even though Retail customer has both prefLabel and altLabel that fuzzy-match,
    # the strategy should keep only the best score per target_uri.
    hits = FuzzyStringStrategy(threshold=0.5).match("retail custmer", glossary)
    uris = [h.target_uri for h in hits]
    assert len(uris) == len(set(uris))


# ---- Embedding (token overlap) ----

def test_embedding_matches_overlapping_tokens(glossary):
    # "customer" overlaps with every multi-word "* customer" concept. The strategy
    # excludes score==1.0 matches (which is bank:Customer's exact "Customer" prefLabel).
    hits = EmbeddingSimilarityStrategy(threshold=0.4).match("customer", glossary)
    uris = [h.target_uri for h in hits]
    assert any(u.endswith("/RetailCustomer") for u in uris)
    assert any(u.endswith("/CorporateCustomer") for u in uris)
    assert all(h.score < 1.0 for h in hits)


def test_embedding_returns_sorted(glossary):
    hits = EmbeddingSimilarityStrategy(threshold=0.3).match("retail customer", glossary)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_embedding_no_overlap_returns_empty(glossary):
    hits = EmbeddingSimilarityStrategy(threshold=0.3).match("xyz qqq", glossary)
    assert hits == []


def test_embedding_accepts_custom_encoder(glossary):
    class IdentityEncoder:
        def encode(self, text):
            return {text.casefold(): 1.0}

    strat = EmbeddingSimilarityStrategy(encoder=IdentityEncoder(), threshold=0.5)
    # An identity-token encoder only fires on the trivial exact-match case;
    # but we filter score == 1.0, so we expect zero results here.
    assert strat.match("Retail customer", glossary) == []


# ---- TokenOverlapEncoder ----

def test_token_overlap_encoder_lowercases_and_tokenizes():
    enc = TokenOverlapEncoder()
    assert dict(enc.encode("Retail PI Customer!")) == {"retail": 1, "pi": 1, "customer": 1}


def test_token_overlap_encoder_counts_repeats():
    enc = TokenOverlapEncoder()
    assert dict(enc.encode("loan loan policy")) == {"loan": 2, "policy": 1}


# ---- Custom in-memory glossary ----

def test_strategies_work_against_arbitrary_glossary():
    g = from_entries([
        GlossaryEntry(uri="ex:Foo", pref_label="Foo bar", alt_labels=("Foobar",)),
        GlossaryEntry(uri="ex:Baz", pref_label="Baz qux"),
    ])
    assert ExactMatchStrategy().match("foobar", g)[0].target_uri == "ex:Foo"
    fuzzy = FuzzyStringStrategy(threshold=0.7).match("Foo barr", g)
    assert fuzzy and fuzzy[0].target_uri == "ex:Foo"
