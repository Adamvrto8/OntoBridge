from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from rdflib import Graph, RDFS, SKOS
from rdflib.term import URIRef


@dataclass
class FiboIndex:
    uri_by_label: dict[str, set[str]] = field(default_factory=dict)
    uri_to_definition: dict[str, str] = field(default_factory=dict)

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
        for subject in set(graph.subjects(predicate=RDFS.label)) | set(
            graph.subjects(predicate=SKOS.altLabel)
        ):
            if not isinstance(subject, URIRef):
                continue
            labels = list(graph.objects(subject=subject, predicate=RDFS.label))
            labels += list(graph.objects(subject=subject, predicate=SKOS.altLabel))
            if not labels:
                continue
            for label in labels:
                if not hasattr(label, "value"):
                    continue
                text = str(label.value).strip()
                normalized = self.normalize_label(text)
                if not normalized:
                    continue
                self.uri_by_label.setdefault(normalized, set()).add(str(subject))

            definition = None
            for candidate in graph.objects(subject=subject, predicate=SKOS.definition):
                definition = str(candidate).strip()
                if definition:
                    break
            if not definition:
                for candidate in graph.objects(subject=subject, predicate=RDFS.comment):
                    definition = str(candidate).strip()
                    if definition:
                        break
            if definition:
                self.uri_to_definition[str(subject)] = definition

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
