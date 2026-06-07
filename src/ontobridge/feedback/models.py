from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class FeedbackEvent:
    event_type: str   # "definition_corrected" | "taxonomy_corrected" | "relation_approved" | "relation_rejected"
    term_label: str
    old_value: str    # agent's original output
    new_value: str    # steward's correction (empty string if rejected/removed)
    actor: str
    term_uri: str = ""
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        if self.event_type not in (
            "definition_corrected",
            "taxonomy_corrected",
            "relation_approved",
            "relation_rejected",
        ):
            raise ValueError(f"Unknown event_type: {self.event_type!r}")
