from __future__ import annotations

import sys
from pathlib import Path

import pytest
from rdflib import Graph

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ontobridge.agents.governance.ontology import OntologyIndex  # noqa: E402

ONTOLOGY_PATH = PROJECT_ROOT / "ontology" / "ontobridge_ontology_v0.1.ttl"


@pytest.fixture(scope="session")
def base_ontology() -> OntologyIndex:
    return OntologyIndex.from_file(ONTOLOGY_PATH)


@pytest.fixture
def ontology_with(base_ontology: OntologyIndex):
    """Return a factory that produces an OntologyIndex augmented with extra triples."""
    def _factory(turtle: str) -> OntologyIndex:
        g = Graph()
        for t in base_ontology.graph:
            g.add(t)
        prefixes = """
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix bank: <http://ontobridge.dev/ontology/bank/> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
"""
        g.parse(data=prefixes + turtle, format="turtle")
        return OntologyIndex(g)
    return _factory
