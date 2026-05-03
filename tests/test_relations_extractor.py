from __future__ import annotations

from ontobridge.agents.relations import (
    DEFAULT_VERB_VOCAB,
    RegexHeuristicExtractor,
    SVOTriple,
)


# ---------- basic SVO extraction ----------

def test_extracts_simple_subject_verb_object():
    triples = RegexHeuristicExtractor().extract("A customer holds a PI loan")
    assert len(triples) == 1
    t = triples[0]
    assert t.subject == "A customer"
    assert t.verb == "holds"
    assert t.object == "a PI loan"


def test_strips_relative_clause_connectors():
    triples = RegexHeuristicExtractor().extract(
        "A retail customer who holds instalment-based credit products"
    )
    assert len(triples) == 1
    t = triples[0]
    assert "retail customer" in t.subject.lower()
    assert t.verb == "holds"
    assert t.object == "instalment-based credit products"


def test_extracts_multiple_verbs_chained_with_and():
    triples = RegexHeuristicExtractor().extract(
        "A customer holds a PI loan and uses the mobile app"
    )
    verbs = [t.verb for t in triples]
    assert verbs == ["holds", "uses"]
    # Subject is shared across chained verbs.
    assert all("customer" in t.subject.lower() for t in triples)
    objects = [t.object for t in triples]
    assert "PI loan" in objects[0]
    assert "mobile app" in objects[1]
    # Connector 'and' between the two clauses must NOT leak into either object.
    assert not objects[0].lower().endswith("and")
    assert not objects[1].lower().startswith("and")


def test_handles_multiple_sentences():
    triples = RegexHeuristicExtractor().extract(
        "Loan application triggers credit check. The bank requires KYC verification."
    )
    verbs = sorted(t.verb for t in triples)
    assert verbs == ["requires", "triggers"]


# ---------- default subject fallback ----------

def test_uses_default_subject_when_clause_has_no_leading_np():
    extractor = RegexHeuristicExtractor()
    # "holds X" alone — no leading subject in the text, so the default kicks in.
    triples = extractor.extract("holds the credit policy", default_subject="bank")
    assert len(triples) == 1
    assert triples[0].subject == "bank"


def test_no_default_subject_yields_no_triples_for_anchorless_clause():
    triples = RegexHeuristicExtractor().extract("holds the credit policy")
    assert triples == []


# ---------- vocabulary controls ----------

def test_unknown_verbs_do_not_emit_triples():
    triples = RegexHeuristicExtractor().extract("Customer pays the bank monthly")
    # 'pays' is not in DEFAULT_VERB_VOCAB
    assert triples == []


def test_custom_vocabulary_changes_what_is_extracted():
    extractor = RegexHeuristicExtractor(vocab={"pays"})
    triples = extractor.extract("Customer pays the bank monthly")
    assert len(triples) == 1
    assert triples[0].verb == "pays"


def test_default_vocab_contains_lexicon_verbs():
    for v in ("holds", "submits", "uses", "evaluates", "requires",
              "produces", "governs", "triggers"):
        assert v in DEFAULT_VERB_VOCAB


def test_default_vocab_contains_unresolved_verb_candidates():
    # Verbs the extractor recognises but the v0.1 lexicon doesn't — the agent
    # needs these to flag steward review.
    for v in ("processes", "approves", "validates"):
        assert v in DEFAULT_VERB_VOCAB


# ---------- edge cases ----------

def test_empty_text_returns_empty_list():
    assert RegexHeuristicExtractor().extract("") == []
    assert RegexHeuristicExtractor().extract("   ") == []


def test_extract_returns_svo_triple_instances():
    triples = RegexHeuristicExtractor().extract("Customer holds product")
    assert all(isinstance(t, SVOTriple) for t in triples)


def test_source_text_preserved_for_traceability():
    triples = RegexHeuristicExtractor().extract(
        "Customer holds a loan. Bank approves application."
    )
    assert triples[0].source_text and "Customer holds" in triples[0].source_text
    assert triples[1].source_text and "Bank approves" in triples[1].source_text


def test_strips_trailing_punctuation_from_object():
    triples = RegexHeuristicExtractor().extract("Customer holds a product.")
    assert triples[0].object == "a product"  # trailing period stripped, articles kept


def test_punctuation_only_clauses_yield_nothing():
    assert RegexHeuristicExtractor().extract("...") == []
