from __future__ import annotations

import pytest

from ontobridge.pipeline_config import PipelineConfig
from ontobridge.pipeline import PipelineRunner
from ontobridge.publisher import InMemoryPublisher


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def test_default_config_has_expected_thresholds():
    cfg = PipelineConfig()
    assert cfg.fuzzy_threshold == 0.75
    assert cfg.embedding_threshold == 0.50
    assert cfg.placement_threshold == 0.50
    assert cfg.sibling_conflict_threshold == 0.80


def test_default_config_encoder_is_none():
    assert PipelineConfig().encoder is None


def test_default_config_ontology_path_points_at_v0_1():
    cfg = PipelineConfig()
    assert cfg.ontology_path.name == "ontobridge_ontology_v0.1.ttl"


def test_default_namespaces():
    cfg = PipelineConfig()
    assert "bank" in cfg.bank_namespace
    assert "relations" in cfg.rel_namespace


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("fuzzy_threshold", -0.1),
    ("fuzzy_threshold", 1.1),
    ("embedding_threshold", -0.01),
    ("placement_threshold", 2.0),
    ("sibling_conflict_threshold", -1.0),
])
def test_out_of_range_threshold_raises(field, value):
    with pytest.raises(ValueError, match=field):
        PipelineConfig(**{field: value})


def test_boundary_values_are_accepted():
    cfg = PipelineConfig(
        fuzzy_threshold=0.0,
        embedding_threshold=1.0,
        placement_threshold=0.0,
        sibling_conflict_threshold=1.0,
    )
    assert cfg.fuzzy_threshold == 0.0
    assert cfg.sibling_conflict_threshold == 1.0


# ---------------------------------------------------------------------------
# Frozen — immutable after construction
# ---------------------------------------------------------------------------

def test_config_is_frozen():
    cfg = PipelineConfig()
    with pytest.raises((AttributeError, TypeError)):
        cfg.fuzzy_threshold = 0.9  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PipelineRunner accepts config and applies thresholds
# ---------------------------------------------------------------------------

def test_runner_applies_config_thresholds(base_ontology):
    cfg = PipelineConfig(fuzzy_threshold=0.9, placement_threshold=0.6)
    runner = PipelineRunner(base_ontology, InMemoryPublisher(), config=cfg)
    assert runner.mapping.fuzzy_threshold == 0.9
    assert runner.taxonomy.placement_threshold == 0.6


def test_runner_config_encoder_forwarded(base_ontology):
    from typing import Mapping

    class StubEncoder:
        def encode(self, text: str) -> Mapping[str, float]:
            return {"0": 1.0}

    enc = StubEncoder()
    cfg = PipelineConfig(encoder=enc)
    runner = PipelineRunner(base_ontology, InMemoryPublisher(), config=cfg)
    assert runner.mapping.embedding.encoder is enc
    assert runner.taxonomy.encoder is enc


def test_runner_config_namespaces_forwarded(base_ontology):
    cfg = PipelineConfig(
        bank_namespace="http://example.com/bank/",
        rel_namespace="http://example.com/rel/",
    )
    runner = PipelineRunner(base_ontology, InMemoryPublisher(), config=cfg)
    assert runner.writer.bank_namespace == "http://example.com/bank/"
    assert runner.writer.rel_namespace == "http://example.com/rel/"


def test_runner_config_takes_precedence_over_encoder_kwarg(base_ontology):
    """When both config and encoder= are given, config wins."""
    from typing import Mapping

    class EncA:
        def encode(self, text: str) -> Mapping[str, float]:
            return {"0": 1.0}

    class EncB:
        def encode(self, text: str) -> Mapping[str, float]:
            return {"0": 0.5}

    enc_a = EncA()
    enc_b = EncB()
    cfg = PipelineConfig(encoder=enc_a)
    runner = PipelineRunner(
        base_ontology, InMemoryPublisher(), encoder=enc_b, config=cfg
    )
    # config.encoder (enc_a) must win
    assert runner.mapping.embedding.encoder is enc_a
