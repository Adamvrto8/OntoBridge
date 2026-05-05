from __future__ import annotations

from ontobridge.audit.base import AuditLog
from ontobridge.audit.models import AuditEntry


class InMemoryAuditLog(AuditLog):
    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    def entries(
        self,
        *,
        term_uri: str | None = None,
        actor: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        result = list(self._entries)
        if term_uri is not None:
            result = [e for e in result if e.term_uri == term_uri]
        if actor is not None:
            result = [e for e in result if e.actor == actor]
        # Newest first
        result.sort(key=lambda e: e.timestamp, reverse=True)
        return result[:limit]

    def count(self) -> int:
        return len(self._entries)
