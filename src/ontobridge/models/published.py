from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from ontobridge.models.enrichment import EnrichedTerm
from ontobridge.models.enums import LifecycleStatus

if TYPE_CHECKING:
    from ontobridge.agents.governance.models import GovResult


_RECOMMENDED_TO_LIFECYCLE: dict[str, LifecycleStatus] = {
    "block": LifecycleStatus.CANDIDATE,
    "draft": LifecycleStatus.DRAFT,
    "review": LifecycleStatus.REVIEW,
    "publish": LifecycleStatus.PUBLISHED,
}


def lifecycle_from_action(action: str) -> LifecycleStatus:
    try:
        return _RECOMMENDED_TO_LIFECYCLE[action]
    except KeyError as exc:
        raise ValueError(
            f"Unknown recommended_action {action!r}; expected one of "
            f"{sorted(_RECOMMENDED_TO_LIFECYCLE)}"
        ) from exc


@dataclass
class PublishedTerm:
    enriched_term: EnrichedTerm
    term_uri: str
    lifecycle_status: LifecycleStatus = LifecycleStatus.CANDIDATE
    approved_by: str | None = None
    published_at: datetime | None = None
    version: int = 1
    turtle: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.enriched_term, EnrichedTerm):
            raise TypeError("PublishedTerm.enriched_term must be an EnrichedTerm")
        if not self.term_uri or not self.term_uri.strip():
            raise ValueError("PublishedTerm.term_uri must be a non-empty string")
        if not isinstance(self.lifecycle_status, LifecycleStatus):
            raise TypeError(
                "PublishedTerm.lifecycle_status must be a LifecycleStatus enum"
            )
        if self.version < 1:
            raise ValueError("PublishedTerm.version must be >= 1")
        if self.lifecycle_status is LifecycleStatus.PUBLISHED and not self.approved_by:
            raise ValueError(
                "PublishedTerm in PUBLISHED status requires approved_by to be set"
            )

    @classmethod
    def from_enriched(
        cls,
        enriched: EnrichedTerm,
        term_uri: str,
        approved_by: str | None = None,
        published_at: datetime | None = None,
    ) -> "PublishedTerm":
        gov = enriched.governance_result
        if gov is None:
            lifecycle = LifecycleStatus.CANDIDATE
        else:
            lifecycle = lifecycle_from_action(gov.recommended_action)
        if lifecycle is LifecycleStatus.PUBLISHED and approved_by is None:
            lifecycle = LifecycleStatus.REVIEW
        return cls(
            enriched_term=enriched,
            term_uri=term_uri,
            lifecycle_status=lifecycle,
            approved_by=approved_by,
            published_at=published_at,
        )
