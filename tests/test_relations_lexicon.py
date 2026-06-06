from __future__ import annotations

from ontobridge.agents.governance.ontology import ObjectPropertyPair
from ontobridge.agents.relations import (
    InverseVerbLexicon,
    LookupDirection,
)


REL_NS = "http://ontobridge.dev/ontology/bank/relations/"


# ---------- ontology integration ----------

def test_lexicon_loads_pairs_from_baseline_ontology(base_ontology):
    lex = InverseVerbLexicon.from_ontology(base_ontology)
    assert len(lex.pairs) == 20
    forwards = {p.forward_label for p in lex.pairs}
    # The original core verbs are still present...
    assert {"holds", "submits", "uses", "evaluates", "requires",
            "produces", "governs", "triggers"} <= forwards
    # ...alongside the expanded secured-lending / compliance verbs.
    assert {"secures", "guarantees", "repays", "owes",
            "verifies", "approves", "classifies"} <= forwards


def test_lexicon_pairs_have_matching_inverses(base_ontology):
    lex = InverseVerbLexicon.from_ontology(base_ontology)
    for pair in lex.pairs:
        # Inverse labels are passive forms — usually "X by", or "X to" for
        # recipient relations (e.g. "charged to").
        assert pair.inverse_label.endswith(" by") or pair.inverse_label.endswith(" to")
        assert pair.forward_uri.startswith(REL_NS)
        assert pair.inverse_uri.startswith(REL_NS)


# ---------- forward lookups ----------

def test_lookup_resolves_forward_verb(base_ontology):
    lex = InverseVerbLexicon.from_ontology(base_ontology)
    hit = lex.lookup("holds")
    assert hit is not None
    assert hit.direction is LookupDirection.FORWARD
    assert hit.predicate_uri == f"{REL_NS}holds"
    assert hit.inverse_predicate_uri == f"{REL_NS}heldBy"


def test_lookup_handles_bare_infinitive(base_ontology):
    lex = InverseVerbLexicon.from_ontology(base_ontology)
    # 'hold' (bare infinitive) should lemmatize to forward label 'holds'.
    hit = lex.lookup("hold")
    assert hit is not None and hit.direction is LookupDirection.FORWARD


def test_lookup_is_case_insensitive(base_ontology):
    lex = InverseVerbLexicon.from_ontology(base_ontology)
    assert lex.lookup("HOLDS") is not None
    assert lex.lookup("  Holds  ") is not None


# ---------- inverse lookups ----------

def test_lookup_resolves_inverse_verb(base_ontology):
    lex = InverseVerbLexicon.from_ontology(base_ontology)
    hit = lex.lookup("held by")
    assert hit is not None
    assert hit.direction is LookupDirection.INVERSE
    assert hit.predicate_uri == f"{REL_NS}heldBy"
    assert hit.inverse_predicate_uri == f"{REL_NS}holds"


def test_lookup_handles_is_X_by_passive_form(base_ontology):
    lex = InverseVerbLexicon.from_ontology(base_ontology)
    hit = lex.lookup("is held by")
    assert hit is not None
    assert hit.direction is LookupDirection.INVERSE


# ---------- unknown verbs ----------

def test_lookup_returns_none_for_unknown_verb(base_ontology):
    lex = InverseVerbLexicon.from_ontology(base_ontology)
    assert lex.lookup("processes") is None
    assert lex.lookup("frobnicates") is None


def test_contains_protocol(base_ontology):
    lex = InverseVerbLexicon.from_ontology(base_ontology)
    assert "holds" in lex
    assert "frobnicates" not in lex


# ---------- direct construction ----------

def test_construct_lexicon_from_explicit_pairs():
    pair = ObjectPropertyPair(
        forward_uri="ex:owns",
        inverse_uri="ex:ownedBy",
        forward_label="owns",
        inverse_label="owned by",
    )
    lex = InverseVerbLexicon([pair])
    forward = lex.lookup("owns")
    assert forward is not None and forward.predicate_uri == "ex:owns"
    inverse = lex.lookup("owned by")
    assert inverse is not None and inverse.predicate_uri == "ex:ownedBy"
