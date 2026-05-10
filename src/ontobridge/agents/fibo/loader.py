from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from rdflib import Graph, RDFS, SKOS, URIRef as _URIRef
from rdflib.term import URIRef

_CMNS_AV = "https://www.omg.org/spec/Commons/AnnotationVocabulary/"
CMNS_SYNONYM      = _URIRef(_CMNS_AV + "synonym")
CMNS_ABBREVIATION = _URIRef(_CMNS_AV + "abbreviation")


@dataclass
class FiboIndex:
    uri_by_label:     dict[str, set[str]]   = field(default_factory=dict)
    uri_to_definition: dict[str, str]       = field(default_factory=dict)
    # synonyms and abbreviations stored per URI so the matcher can expose
    # them as alt labels without mixing them into the preferred label slot
    alt_labels_by_uri: dict[str, list[str]] = field(default_factory=dict)

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

            # --- definition ---
            if uri not in self.uri_to_definition:
                definition = self._first_literal(graph, subject, SKOS.definition)
                if not definition:
                    definition = self._first_literal(graph, subject, RDFS.comment)
                if definition:
                    self.uri_to_definition[uri] = definition

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
