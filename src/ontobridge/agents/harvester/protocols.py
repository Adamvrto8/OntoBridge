from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ontobridge.models.enums import SourceType


@dataclass
class RawDocument:
    """A chunk of text extracted from a source, optionally tagged with location."""
    text: str
    section: str | None = None
    page: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedTerm:
    """A candidate term + definition pair pulled from a RawDocument."""
    candidate_label: str
    definition: str
    section: str | None = None
    confidence: float = 0.8
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class DocumentReader(Protocol):
    """Reads a source (file path, URL, or identifier) into RawDocument chunks."""
    source_type: SourceType

    def can_read(self, source: Path | str) -> bool:
        """Return True if this reader handles the given source."""
        ...

    def read(self, source: Path | str) -> list[RawDocument]:
        """Parse the source and return a list of RawDocument chunks."""
        ...


@runtime_checkable
class TermExtractor(Protocol):
    """Extracts (label, definition) pairs from a RawDocument."""

    def extract(self, doc: RawDocument) -> list[ExtractedTerm]:
        ...
