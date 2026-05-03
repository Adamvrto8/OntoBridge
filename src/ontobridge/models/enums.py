from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    CATALOG = "catalog"
    POLICY_DOC = "policy_doc"
    CONTRACT = "contract"
    DATA_PRODUCT = "data_product"
    WIKI = "wiki"
    COMMUNICATION = "communication"
    USER_INPUT = "user_input"


class Tier(str, Enum):
    STRUCTURED = "structured"
    DOCUMENT = "document"
    UNSTRUCTURED = "unstructured"


class MatchType(str, Enum):
    DUPLICATE = "duplicate"
    FUZZY = "fuzzy"
    NEW = "new"


class LifecycleStatus(str, Enum):
    CANDIDATE = "candidate"
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class PlacementStatus(str, Enum):
    PLACED = "placed"
    UNRESOLVED = "unresolved"


class RelationStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED_VERB = "unresolved_verb"
