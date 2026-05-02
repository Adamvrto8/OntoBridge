from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FIBOMatch:
    uri: str
    expected_definition: str | None = None

    def __post_init__(self) -> None:
        if not self.uri or not self.uri.strip():
            raise ValueError("FIBOMatch.uri must be a non-empty string")
