from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ontobridge.models.enums import MatchType, PlacementStatus, RelationStatus
from ontobridge.models.fibo import FIBOMatch
from ontobridge.models.source import HarvestRecord

if TYPE_CHECKING:
    from ontobridge.agents.governance.models import GovResult


@dataclass
class CandidateLabel:
    text: str
    confidence: float
    ner_label: str | None = None

    def __post_init__(self) -> None:
        if not self.text or not self.text.strip():
            raise ValueError("CandidateLabel.text must be a non-empty string")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("CandidateLabel.confidence must be in [0.0, 1.0]")


@dataclass
class PolicyContext:
    paragraph: str
    document_ref: str
    section: str | None = None
    chunk_id: str | None = None
    similarity: float | None = None

    def __post_init__(self) -> None:
        if not self.paragraph or not self.paragraph.strip():
            raise ValueError("PolicyContext.paragraph must be a non-empty string")
        if not self.document_ref or not self.document_ref.strip():
            raise ValueError("PolicyContext.document_ref must be a non-empty string")
        if self.similarity is not None and not 0.0 <= self.similarity <= 1.0:
            raise ValueError("PolicyContext.similarity must be in [0.0, 1.0]")


@dataclass
class MatchResult:
    match_type: MatchType
    similarity: float
    target_uri: str | None = None
    alternative_matches: list[tuple[str, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.match_type, MatchType):
            raise TypeError("MatchResult.match_type must be a MatchType enum")
        if not 0.0 <= self.similarity <= 1.0:
            raise ValueError("MatchResult.similarity must be in [0.0, 1.0]")
        if self.match_type is MatchType.DUPLICATE and not self.target_uri:
            raise ValueError(
                "MatchResult.target_uri is required when match_type is DUPLICATE"
            )


@dataclass(frozen=True)
class SiblingConflict:
    sibling_uri: str
    sibling_label: str
    similarity: float

    def __post_init__(self) -> None:
        if not self.sibling_uri or not self.sibling_uri.strip():
            raise ValueError("SiblingConflict.sibling_uri must be non-empty")
        if not 0.0 <= self.similarity <= 1.0:
            raise ValueError("SiblingConflict.similarity must be in [0.0, 1.0]")


@dataclass
class TaxonomyPlacement:
    broader_concept_uri: str | None
    scheme_uri: str | None
    domain_prefix: str | None = None
    placement_confidence: float = 1.0
    status: PlacementStatus = PlacementStatus.PLACED
    sibling_conflicts: list[SiblingConflict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status is PlacementStatus.PLACED:
            if not self.broader_concept_uri or not self.broader_concept_uri.strip():
                raise ValueError(
                    "TaxonomyPlacement(status=PLACED) requires broader_concept_uri"
                )
            if not self.scheme_uri or not self.scheme_uri.strip():
                raise ValueError(
                    "TaxonomyPlacement(status=PLACED) requires scheme_uri"
                )
        if not 0.0 <= self.placement_confidence <= 1.0:
            raise ValueError(
                "TaxonomyPlacement.placement_confidence must be in [0.0, 1.0]"
            )


@dataclass
class BusinessRule:
    rule_text: str
    condition: str | None = None
    consequence: str | None = None

    def __post_init__(self) -> None:
        if not self.rule_text or not self.rule_text.strip():
            raise ValueError("BusinessRule.rule_text must be a non-empty string")


@dataclass
class SemanticRelation:
    subject_uri: str
    predicate_uri: str | None
    object_label: str
    inverse_predicate_uri: str | None
    verb: str
    confidence: float = 1.0
    status: RelationStatus = RelationStatus.RESOLVED
    object_uri: str | None = None
    source: str | None = None  # "fibo" | "llm" | "svo"

    def __post_init__(self) -> None:
        if not self.subject_uri or not self.subject_uri.strip():
            raise ValueError("SemanticRelation.subject_uri must be non-empty")
        if not self.object_label or not self.object_label.strip():
            raise ValueError("SemanticRelation.object_label must be non-empty")
        if not self.verb or not self.verb.strip():
            raise ValueError("SemanticRelation.verb must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("SemanticRelation.confidence must be in [0.0, 1.0]")
        if self.status is RelationStatus.RESOLVED:
            if not self.predicate_uri or not self.inverse_predicate_uri:
                raise ValueError(
                    "SemanticRelation(status=RESOLVED) requires both predicate_uri and "
                    "inverse_predicate_uri"
                )


@dataclass
class EnrichedTerm:
    harvest_record: HarvestRecord
    candidate_labels: list[CandidateLabel] = field(default_factory=list)
    policy_context: list[PolicyContext] = field(default_factory=list)
    match_result: MatchResult | None = None
    taxonomy_placement: TaxonomyPlacement | None = None
    definition: str | None = None
    business_rules: list[BusinessRule] = field(default_factory=list)
    relations: list[SemanticRelation] = field(default_factory=list)
    fibo_match: FIBOMatch | None = None
    governance_result: "GovResult | None" = None

    @classmethod
    def from_harvest(cls, record: HarvestRecord) -> "EnrichedTerm":
        return cls(harvest_record=record)

    @property
    def preferred_label(self) -> str | None:
        if not self.candidate_labels:
            return None
        return max(self.candidate_labels, key=lambda c: c.confidence).text
