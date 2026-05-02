from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ontobridge.models.enums import SourceType, Tier


@dataclass
class SourceRef:
    source_system: str
    document_id: str | None = None
    section: str | None = None
    uri: str | None = None

    def __post_init__(self) -> None:
        if not self.source_system or not self.source_system.strip():
            raise ValueError("SourceRef.source_system must be a non-empty string")

    def fingerprint(self) -> str:
        parts = [
            self.source_system,
            self.document_id or "",
            self.section or "",
            self.uri or "",
        ]
        return "|".join(parts)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class HarvestRecord:
    text: str
    source_type: SourceType
    source_ref: SourceRef
    confidence: float = 1.0
    tier: Tier = Tier.STRUCTURED
    timestamp: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)
    record_id: str = ""

    def __post_init__(self) -> None:
        if not self.text or not self.text.strip():
            raise ValueError("HarvestRecord.text must be a non-empty string")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"HarvestRecord.confidence must be in [0.0, 1.0]; got {self.confidence}"
            )
        if not isinstance(self.source_type, SourceType):
            raise TypeError("HarvestRecord.source_type must be a SourceType enum")
        if not isinstance(self.tier, Tier):
            raise TypeError("HarvestRecord.tier must be a Tier enum")
        if not isinstance(self.source_ref, SourceRef):
            raise TypeError("HarvestRecord.source_ref must be a SourceRef instance")
        if not self.record_id:
            self.record_id = self._generate_id()

    def _generate_id(self) -> str:
        h = hashlib.sha256()
        h.update(self.text.encode("utf-8"))
        h.update(b"\x00")
        h.update(self.source_ref.fingerprint().encode("utf-8"))
        h.update(b"\x00")
        h.update(self.source_type.value.encode("utf-8"))
        return h.hexdigest()[:16]
