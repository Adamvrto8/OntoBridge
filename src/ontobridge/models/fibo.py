from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FIBOMatch:
    uri: str
    expected_definition: str | None = None
    alt_labels: list[str] = field(default_factory=list)
    broader_uri: str | None = None
    broader_label: str | None = None
    module: str | None = None
    match_type: str = "exact"  # "exact" | "close" | "broad"

    def __post_init__(self) -> None:
        if not self.uri or not self.uri.strip():
            raise ValueError("FIBOMatch.uri must be a non-empty string")
        if self.match_type not in ("exact", "close", "broad"):
            raise ValueError("FIBOMatch.match_type must be 'exact', 'close', or 'broad'")
