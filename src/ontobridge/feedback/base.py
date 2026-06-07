from __future__ import annotations

from abc import ABC, abstractmethod

from ontobridge.feedback.models import FeedbackEvent


class FeedbackStore(ABC):
    @abstractmethod
    def record(self, event: FeedbackEvent) -> None: ...

    @abstractmethod
    def get_examples(self, event_type: str, limit: int = 5) -> list[FeedbackEvent]: ...
