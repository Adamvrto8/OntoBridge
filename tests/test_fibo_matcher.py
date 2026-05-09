from __future__ import annotations

from pathlib import Path

from ontobridge.agents.fibo import FiboIndex, FiboMatcher
from ontobridge.models.fibo import FIBOMatch


def test_fibo_matcher_returns_match_for_known_label(tmp_path):
    graph_path = tmp_path / "sample.ttl"
    graph_path.write_text(
        '''
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix skos: <http://www.w3.org/2004/02/skos/core#> .
        <http://example.org/fibo/Term> a <http://example.org/Concept> ;
            rdfs:label "Retail Customer" ;
            skos:definition "A customer who uses retail banking services." .
        ''',
        encoding="utf-8",
    )

    index = FiboIndex.from_paths([graph_path])
    matcher = FiboMatcher(index)

    match = matcher.match("Retail Customer", "A customer who uses retail banking services.")

    assert isinstance(match, FIBOMatch)
    assert match.uri == "http://example.org/fibo/Term"
    assert match.expected_definition == "A customer who uses retail banking services."


def test_fibo_matcher_returns_none_for_unknown_label(tmp_path):
    graph_path = tmp_path / "sample.ttl"
    graph_path.write_text(
        '''
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        <http://example.org/fibo/Term> rdfs:label "Some Other Term" .
        ''',
        encoding="utf-8",
    )

    index = FiboIndex.from_paths([graph_path])
    matcher = FiboMatcher(index)

    assert matcher.match("Retail Customer", None) is None
