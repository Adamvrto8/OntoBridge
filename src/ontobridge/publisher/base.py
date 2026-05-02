from __future__ import annotations

from abc import ABC, abstractmethod

from ontobridge.models.enums import LifecycleStatus
from ontobridge.models.published import PublishedTerm


class TermNotFoundError(KeyError):
    """Raised when a publisher cannot locate a term by its identifier."""


class TermPublisher(ABC):
    @abstractmethod
    def create_term(self, term: PublishedTerm) -> str:
        ...

    @abstractmethod
    def update_term(self, term_id: str, term: PublishedTerm) -> PublishedTerm:
        ...

    @abstractmethod
    def get_term(self, term_id: str) -> PublishedTerm:
        ...

    @abstractmethod
    def search_terms(self, query: str) -> list[PublishedTerm]:
        ...

    @abstractmethod
    def transition_status(
        self, term_id: str, new_status: LifecycleStatus
    ) -> PublishedTerm:
        ...
