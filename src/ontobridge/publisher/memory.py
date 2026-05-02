from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from ontobridge.models.enums import LifecycleStatus
from ontobridge.models.published import PublishedTerm
from ontobridge.publisher.base import TermNotFoundError, TermPublisher

ALLOWED_TRANSITIONS: dict[LifecycleStatus, set[LifecycleStatus]] = {
    LifecycleStatus.CANDIDATE: {LifecycleStatus.DRAFT, LifecycleStatus.REVIEW},
    LifecycleStatus.DRAFT: {LifecycleStatus.REVIEW, LifecycleStatus.CANDIDATE},
    LifecycleStatus.REVIEW: {
        LifecycleStatus.PUBLISHED,
        LifecycleStatus.DRAFT,
        LifecycleStatus.CANDIDATE,
    },
    LifecycleStatus.PUBLISHED: {LifecycleStatus.DEPRECATED, LifecycleStatus.REVIEW},
    LifecycleStatus.DEPRECATED: set(),
}


class InMemoryPublisher(TermPublisher):
    def __init__(self) -> None:
        self._store: dict[str, PublishedTerm] = {}

    def create_term(self, term: PublishedTerm) -> str:
        if term.term_uri in self._store:
            raise ValueError(
                f"Term with URI {term.term_uri!r} already exists; use update_term"
            )
        self._store[term.term_uri] = deepcopy(term)
        return term.term_uri

    def update_term(self, term_id: str, term: PublishedTerm) -> PublishedTerm:
        if term_id not in self._store:
            raise TermNotFoundError(term_id)
        existing = self._store[term_id]
        new_version = replace(
            term,
            term_uri=term_id,
            version=existing.version + 1,
        )
        self._store[term_id] = deepcopy(new_version)
        return deepcopy(new_version)

    def get_term(self, term_id: str) -> PublishedTerm:
        if term_id not in self._store:
            raise TermNotFoundError(term_id)
        return deepcopy(self._store[term_id])

    def search_terms(self, query: str) -> list[PublishedTerm]:
        if not query:
            return [deepcopy(t) for t in self._store.values()]
        needle = query.casefold()
        results: list[PublishedTerm] = []
        for term in self._store.values():
            haystacks: list[str] = [term.term_uri]
            haystacks.extend(c.text for c in term.enriched_term.candidate_labels)
            if term.enriched_term.definition:
                haystacks.append(term.enriched_term.definition)
            if any(needle in h.casefold() for h in haystacks):
                results.append(deepcopy(term))
        return results

    def transition_status(
        self, term_id: str, new_status: LifecycleStatus
    ) -> PublishedTerm:
        if term_id not in self._store:
            raise TermNotFoundError(term_id)
        existing = self._store[term_id]
        allowed = ALLOWED_TRANSITIONS[existing.lifecycle_status]
        if new_status not in allowed and new_status is not existing.lifecycle_status:
            raise ValueError(
                f"Illegal transition {existing.lifecycle_status.value} -> "
                f"{new_status.value} for term {term_id!r}"
            )
        updated = replace(existing, lifecycle_status=new_status)
        self._store[term_id] = updated
        return deepcopy(updated)
