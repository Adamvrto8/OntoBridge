from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FIBOMatch:
    uri: str
    expected_definition: str | None = None
    alt_labels: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.uri or not self.uri.strip():
            raise ValueError("FIBOMatch.uri must be a non-empty string")
