from __future__ import annotations

from abc import ABC, abstractmethod

from ontobridge.audit.models import AuditEntry


class AuditLog(ABC):
    @abstractmethod
    def record(self, entry: AuditEntry) -> None: ...

    @abstractmethod
    def entries(
        self,
        *,
        term_uri: str | None = None,
        actor: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]: ...

    @abstractmethod
    def count(self) -> int: ...
