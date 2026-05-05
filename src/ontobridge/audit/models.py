from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ontobridge.models.enums import LifecycleStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AuditEntry:
    term_uri: str
    term_label: str
    action: str
    actor: str
    previous_status: LifecycleStatus
    new_status: LifecycleStatus
    timestamp: datetime = field(default_factory=_utc_now)
    comment: str | None = None
    entry_id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.term_uri or not self.term_uri.strip():
            raise ValueError("AuditEntry.term_uri must be non-empty")
        if not self.action or not self.action.strip():
            raise ValueError("AuditEntry.action must be non-empty")
        if not self.actor or not self.actor.strip():
            raise ValueError("AuditEntry.actor must be non-empty")
        if not self.entry_id:
            self.entry_id = self._generate_id()

    def _generate_id(self) -> str:
        h = hashlib.sha256()
        h.update(self.term_uri.encode())
        h.update(self.action.encode())
        h.update(self.actor.encode())
        h.update(self.timestamp.isoformat().encode())
        return h.hexdigest()[:16]
