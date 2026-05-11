from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from rdflib import Graph, RDFS, SKOS, OWL, URIRef as _URIRef
from rdflib.term import URIRef, BNode

_CMNS_AV = "https://www.omg.org/spec/Commons/AnnotationVocabulary/"
CMNS_SYNONYM      = _URIRef(_CMNS_AV + "synonym")
CMNS_ABBREVIATION = _URIRef(_CMNS_AV + "abbreviation")


@dataclass
class FiboIndex:
    uri_by_label:      dict[str, set[str]]   = field(default_factory=dict)
    uri_to_definition: dict[str, str]        = field(default_factory=dict)
    alt_labels_by_uri: dict[str, list[str]]  = field(default_factory=dict)
    # preferred label for each URI — used to resolve parent labels
    label_by_uri:      dict[str, str]        = field(default_factory=dict)
    # direct parent URI from rdfs:subClassOf (named classes only, no BNodes)
    parent_by_uri:     dict[str, str]        = field(default_factory=dict)

    @classmethod
    def from_paths(cls, paths: Iterable[Path | str]) -> "FiboIndex":
        index = cls()
        for path in paths:
            index.update_from_path(Path(path))
        return index

    @classmethod
    def from_graph(cls, graph: Graph) -> "FiboIndex":
        index = cls()
        index._index_graph(graph)
        return index

    def update_from_path(self, path: Path) -> None:
        graph = Graph()
        graph.parse(str(path), format=self._format_for_path(path))
        self._index_graph(graph)

    def _index_graph(self, graph: Graph) -> None:
        all_subjects = (
            set(graph.subjects(predicate=RDFS.label))
            | set(graph.subjects(predicate=SKOS.altLabel))
            | set(graph.subjects(predicate=CMNS_SYNONYM))
            | set(graph.subjects(predicate=CMNS_ABBREVIATION))
        )

        for subject in all_subjects:
            if not isinstance(subject, URIRef):
                continue
            uri = str(subject)

            # --- preferred / alt labels (for matching) ---
            pref_labels = list(graph.objects(subject=subject, predicate=RDFS.label))
            alt_labels  = list(graph.objects(subject=subject, predicate=SKOS.altLabel))
            for label in pref_labels + alt_labels:
                text = self._label_text(label)
                if text:
                    self.uri_by_label.setdefault(text, set()).add(uri)

            # --- synonyms (for matching AND alt label population) ---
            synonyms: list[str] = []
            for label in graph.objects(subject=subject, predicate=CMNS_SYNONYM):
                text = self._label_text(label)
                if text:
                    self.uri_by_label.setdefault(text, set()).add(uri)
                    synonyms.append(text)

            # --- abbreviations (for matching AND alt label population) ---
            abbreviations: list[str] = []
            for label in graph.objects(subject=subject, predicate=CMNS_ABBREVIATION):
                text = self._label_text(label)
                if text:
                    self.uri_by_label.setdefault(text, set()).add(uri)
                    abbreviations.append(text)

            if synonyms or abbreviations:
                existing = self.alt_labels_by_uri.get(uri, [])
                merged = existing + synonyms + abbreviations
                # deduplicate while preserving order
                seen: set[str] = set(existing)
                unique: list[str] = list(existing)
                for lbl in synonyms + abbreviations:
                    if lbl not in seen:
                        seen.add(lbl)
                        unique.append(lbl)
                self.alt_labels_by_uri[uri] = unique

            # --- preferred label (for parent label lookup) ---
            if uri not in self.label_by_uri:
                for lbl in graph.objects(subject=subject, predicate=RDFS.label):
                    text = self._label_text(lbl)
                    if text:
                        self.label_by_uri[uri] = text
                        break

            # --- definition ---
            if uri not in self.uri_to_definition:
                definition = self._first_literal(graph, subject, SKOS.definition)
                if not definition:
                    definition = self._first_literal(graph, subject, RDFS.comment)
                if definition:
                    self.uri_to_definition[uri] = definition

        # --- rdfs:subClassOf hierarchy (named classes only, skip BNodes) ---
        for subject, _, obj in graph.triples((None, RDFS.subClassOf, None)):
            if isinstance(subject, URIRef) and isinstance(obj, URIRef):
                s, o = str(subject), str(obj)
                # only store the first parent found; skip owl:Thing
                if s not in self.parent_by_uri and "owl#Thing" not in o:
                    self.parent_by_uri[s] = o

    @staticmethod
    def _label_text(node) -> str:
        if hasattr(node, "value"):
            return node.value.strip().casefold()
        text = str(node).strip().casefold()
        return " ".join(text.split()) if text else ""

    @staticmethod
    def _first_literal(graph: Graph, subject: URIRef, predicate) -> str:
        for obj in graph.objects(subject=subject, predicate=predicate):
            text = str(obj).strip()
            if text:
                return text
        return ""

    @staticmethod
    def normalize_label(label: str) -> str:
        return " ".join(label.strip().casefold().split())

    @staticmethod
    def _format_for_path(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".ttl", ".n3"}:
            return "turtle"
        if suffix in {".rdf", ".owl", ".xml"}:
            return "xml"
        if suffix == ".nt":
            return "nt"
        if suffix == ".jsonld":
            return "json-ld"
        return "turtle"
