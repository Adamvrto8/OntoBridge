from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ontobridge.agents.mapping.strategies import (
    DEFAULT_EMBEDDING_THRESHOLD,
    DEFAULT_FUZZY_THRESHOLD,
    Encoder,
)
from ontobridge.agents.taxonomy.agent import (
    DEFAULT_PLACEMENT_THRESHOLD,
    DEFAULT_SIBLING_CONFLICT_THRESHOLD,
)

# Default ontology path — same resolution as DashboardConfig uses
_DEFAULT_ONTOLOGY = (
    Path(__file__).resolve().parents[2] / "ontology" / "ontobridge_ontology_v0.1.ttl"
)


@dataclass(frozen=True)
class PipelineConfig:
    """Single source of truth for all tuneable pipeline parameters.

    Pass an instance to ``PipelineRunner`` to override any default without
    touching individual agent constructors.

    Attributes:
        ontology_path: Path to the ``.ttl`` file loaded into OntologyIndex.
        fuzzy_threshold: Minimum SequenceMatcher ratio for FuzzyStringStrategy
            to emit a match (0–1, default 0.75).
        embedding_threshold: Minimum cosine similarity for
            EmbeddingSimilarityStrategy to emit a match (0–1, default 0.50).
        placement_threshold: Minimum similarity for TaxonomyAgent to accept a
            parent concept placement (0–1, default 0.50).
        sibling_conflict_threshold: Similarity above which an existing sibling
            is flagged as a conflict (0–1, default 0.80).
        encoder: Optional dense encoder shared by MappingAgent and TaxonomyAgent.
            When ``None`` the TokenOverlapEncoder fallback is used.
        bank_namespace: Base URI for new bank concept terms emitted by WriterAgent.
        rel_namespace: Base URI for relation predicates emitted by WriterAgent.
    """

    ontology_path: Path = field(default=_DEFAULT_ONTOLOGY)

    # Mapping agent
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD
    embedding_threshold: float = DEFAULT_EMBEDDING_THRESHOLD

    # Taxonomy agent
    placement_threshold: float = DEFAULT_PLACEMENT_THRESHOLD
    sibling_conflict_threshold: float = DEFAULT_SIBLING_CONFLICT_THRESHOLD

    # Shared encoder — not part of frozen hash (mutable object), excluded via field
    encoder: Encoder | None = field(default=None, hash=False, compare=False)

    # Policy Linker
    policy_linker_threshold: float = 0.60
    policy_linker_top_k: int = 3

    # Upsert / drift (steady-state ingestion)
    # merge_threshold: minimum fuzzy similarity for an incoming term to be merged
    #   into an already-published term instead of creating a new one. DUPLICATE
    #   (exact-label) matches always merge regardless of this value.
    # drift_threshold: definition similarity below which a merged term is flagged
    #   for steward review (the new document defines the term differently).
    merge_threshold: float = 0.92
    drift_threshold: float = 0.85

    # Writer agent namespaces
    bank_namespace: str = "http://ontobridge.dev/ontology/bank/"
    rel_namespace: str = "http://ontobridge.dev/ontology/bank/relations/"

    def __post_init__(self) -> None:
        for name, val in [
            ("fuzzy_threshold", self.fuzzy_threshold),
            ("embedding_threshold", self.embedding_threshold),
            ("placement_threshold", self.placement_threshold),
            ("sibling_conflict_threshold", self.sibling_conflict_threshold),
            ("policy_linker_threshold", self.policy_linker_threshold),
            ("merge_threshold", self.merge_threshold),
            ("drift_threshold", self.drift_threshold),
        ]:
            if not 0.0 <= val <= 1.0:
                raise ValueError(f"{name} must be in [0.0, 1.0]; got {val}")
