from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS


@dataclass(frozen=True)
class ObjectPropertyPair:
    forward_uri: str
    inverse_uri: str
    forward_label: str
    inverse_label: str


@dataclass(frozen=True)
class ConceptRecord:
    uri: str
    pref_label: str
    alt_labels: tuple[str, ...]
    definition: str | None
    scheme: str | None
    scheme_label: str | None
    exact_matches: tuple[str, ...]
    close_matches: tuple[str, ...]
    deprecated: bool


class OntologyIndex:
    def __init__(self, graph: Graph):
        self.graph = graph
        self._concepts: list[ConceptRecord] = self._build_index()
        self._scheme_labels: dict[str, str] = self._build_scheme_labels()

    @classmethod
    def from_file(cls, path: str | Path) -> "OntologyIndex":
        g = Graph()
        g.parse(str(path), format="turtle")
        return cls(g)

    def _build_scheme_labels(self) -> dict[str, str]:
        labels: dict[str, str] = {}
        for scheme in self.graph.subjects(RDF.type, SKOS.ConceptScheme):
            label = self.graph.value(scheme, SKOS.prefLabel)
            if label is not None:
                labels[str(scheme)] = str(label)
        return labels

    def _build_index(self) -> list[ConceptRecord]:
        records: list[ConceptRecord] = []
        for concept in self.graph.subjects(RDF.type, SKOS.Concept):
            pref = self.graph.value(concept, SKOS.prefLabel)
            if pref is None:
                continue
            alts = tuple(str(o) for o in self.graph.objects(concept, SKOS.altLabel))
            definition = self.graph.value(concept, SKOS.definition)
            scheme = self.graph.value(concept, SKOS.inScheme)
            scheme_uri = str(scheme) if scheme else None
            scheme_label = None
            if scheme is not None:
                lbl = self.graph.value(scheme, SKOS.prefLabel)
                if lbl is not None:
                    scheme_label = str(lbl)
            exacts = tuple(str(o) for o in self.graph.objects(concept, SKOS.exactMatch))
            closes = tuple(str(o) for o in self.graph.objects(concept, SKOS.closeMatch))
            deprecated = (concept, OWL.deprecated, Literal(True)) in self.graph
            records.append(
                ConceptRecord(
                    uri=str(concept),
                    pref_label=str(pref),
                    alt_labels=alts,
                    definition=str(definition) if definition is not None else None,
                    scheme=scheme_uri,
                    scheme_label=scheme_label,
                    exact_matches=exacts,
                    close_matches=closes,
                    deprecated=deprecated,
                )
            )
        return records

    @property
    def concepts(self) -> list[ConceptRecord]:
        return list(self._concepts)

    def find_by_pref_label(self, label: str) -> ConceptRecord | None:
        target = label.casefold()
        for c in self._concepts:
            if c.pref_label.casefold() == target:
                return c
        return None

    def find_by_any_label(self, label: str) -> list[ConceptRecord]:
        target = label.casefold()
        out: list[ConceptRecord] = []
        for c in self._concepts:
            if c.pref_label.casefold() == target:
                out.append(c)
                continue
            if any(a.casefold() == target for a in c.alt_labels):
                out.append(c)
        return out

    def find_by_acronym(self, acronym: str) -> list[ConceptRecord]:
        if not acronym:
            return []
        ac = acronym.upper()
        matches: list[ConceptRecord] = []
        for c in self._concepts:
            tokens = [t for t in c.pref_label.split() if t and t[0].isalpha()]
            if not tokens:
                continue
            initials = "".join(t[0].upper() for t in tokens)
            if initials == ac and len(tokens) >= 2:
                matches.append(c)
                continue
            if any(a.upper() == ac for a in c.alt_labels):
                matches.append(c)
        return matches

    def find_deprecated_by_label(self, label: str) -> list[ConceptRecord]:
        target = label.casefold()
        return [c for c in self._concepts if c.deprecated and (
            c.pref_label.casefold() == target
            or any(a.casefold() == target for a in c.alt_labels)
        )]

    def scheme_label(self, scheme_uri: str) -> str | None:
        return self._scheme_labels.get(scheme_uri)

    def by_uri(self, concept_uri: str) -> ConceptRecord | None:
        for c in self._concepts:
            if c.uri == concept_uri:
                return c
        return None

    def get_broader(self, concept_uri: str) -> str | None:
        val = self.graph.value(URIRef(concept_uri), SKOS.broader)
        return str(val) if val is not None else None

    def get_narrower(self, concept_uri: str) -> list[str]:
        return [str(s) for s in self.graph.subjects(SKOS.broader, URIRef(concept_uri))]

    def is_top_concept(self, concept_uri: str) -> bool:
        return (URIRef(concept_uri), SKOS.topConceptOf, None) in self.graph or any(
            self.graph.objects(URIRef(concept_uri), SKOS.topConceptOf)
        )

    def object_property_pairs(self) -> list[ObjectPropertyPair]:
        seen: set[tuple[str, str]] = set()
        pairs: list[ObjectPropertyPair] = []
        for prop in self.graph.subjects(RDF.type, OWL.ObjectProperty):
            inverse = self.graph.value(prop, OWL.inverseOf)
            if inverse is None:
                continue
            f_label = self.graph.value(prop, RDFS.label)
            i_label = self.graph.value(inverse, RDFS.label)
            if f_label is None or i_label is None:
                continue
            key = tuple(sorted((str(prop), str(inverse))))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(
                ObjectPropertyPair(
                    forward_uri=str(prop),
                    inverse_uri=str(inverse),
                    forward_label=str(f_label),
                    inverse_label=str(i_label),
                )
            )
        return pairs


def load_ontology(path: str | Path) -> OntologyIndex:
    return OntologyIndex.from_file(path)
