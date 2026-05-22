from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Protocol, runtime_checkable

from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.models.published import PublishedTerm
from ontobridge.publisher.base import TermPublisher


@dataclass(frozen=True)
class GlossaryEntry:
    uri: str
    pref_label: str
    alt_labels: tuple[str, ...] = ()
    definition: str | None = None


@runtime_checkable
class GlossarySource(Protocol):
    def entries(self) -> Iterator[GlossaryEntry]: ...


class ListGlossarySource:
    def __init__(self, entries: Iterable[GlossaryEntry]):
        self._entries: tuple[GlossaryEntry, ...] = tuple(entries)

    def entries(self) -> Iterator[GlossaryEntry]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


def from_entries(entries: Iterable[GlossaryEntry]) -> ListGlossarySource:
    return ListGlossarySource(entries)


def from_ontology(index: OntologyIndex) -> ListGlossarySource:
    return ListGlossarySource(
        GlossaryEntry(
            uri=c.uri,
            pref_label=c.pref_label,
            alt_labels=c.alt_labels,
            definition=c.definition,
        )
        for c in index.concepts
    )


def from_published_terms(terms: Iterable[PublishedTerm]) -> ListGlossarySource:
    out: list[GlossaryEntry] = []
    for term in terms:
        labels = sorted(
            term.enriched_term.candidate_labels,
            key=lambda c: c.confidence,
            reverse=True,
        )
        if not labels:
            continue
        out.append(
            GlossaryEntry(
                uri=term.term_uri,
                pref_label=labels[0].text,
                alt_labels=tuple(c.text for c in labels[1:]),
                definition=term.enriched_term.definition,
            )
        )
    return ListGlossarySource(out)


def from_publisher(publisher: TermPublisher) -> ListGlossarySource:
    return from_published_terms(publisher.search_terms(""))


class PublisherGlossarySource:
    """Live glossary backed by the publisher.

    Re-reads published terms on every ``entries()`` call so that terms
    published earlier in the same batch are visible when checking
    subsequent terms.  This is the key property that enables both
    cross-document and within-document deduplication.
    """

    def __init__(self, publisher: TermPublisher) -> None:
        self._publisher = publisher

    def entries(self) -> Iterator[GlossaryEntry]:
        yield from from_published_terms(self._publisher.search_terms("")).entries()


class CombinedGlossarySource:
    """Chains multiple GlossarySources into one.

    Used to check an incoming term against both the static ontology
    concepts *and* the live published glossary in a single pass.
    """

    def __init__(self, *sources: GlossarySource) -> None:
        self._sources = sources

    def entries(self) -> Iterator[GlossaryEntry]:
        for source in self._sources:
            yield from source.entries()
