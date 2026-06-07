from __future__ import annotations

from ontobridge.feedback.base import FeedbackStore
from ontobridge.feedback.models import FeedbackEvent


class InMemoryFeedbackStore(FeedbackStore):
    def __init__(self) -> None:
        self._events: list[FeedbackEvent] = []

    def record(self, event: FeedbackEvent) -> None:
        self._events.append(event)

    def get_examples(self, event_type: str, limit: int = 5) -> list[FeedbackEvent]:
        matching = [e for e in self._events if e.event_type == event_type]
        return matching[-limit:]
