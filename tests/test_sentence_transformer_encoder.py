from __future__ import annotations

import pytest

st = pytest.importorskip(
    "sentence_transformers",
    reason="sentence-transformers not installed; skipping encoder tests",
)

from ontobridge.encoders import SentenceTransformerEncoder  # noqa: E402
from ontobridge.agents.mapping.strategies import Encoder  # noqa: E402


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

def test_satisfies_encoder_protocol():
    enc = SentenceTransformerEncoder()
    assert isinstance(enc, Encoder)


# ---------------------------------------------------------------------------
# Output shape and type
# ---------------------------------------------------------------------------

def test_encode_returns_mapping_of_str_to_float():
    enc = SentenceTransformerEncoder()
    result = enc.encode("retail customer")
    assert isinstance(result, dict)
    assert all(isinstance(k, str) for k in result)
    assert all(isinstance(v, float) for v in result.values())


def test_encode_dimension_keys_are_sequential_integers():
    enc = SentenceTransformerEncoder()
    result = enc.encode("loan repayment")
    keys = sorted(int(k) for k in result)
    assert keys == list(range(len(keys)))


def test_encode_returns_384_dimensions_for_minilm():
    enc = SentenceTransformerEncoder()
    result = enc.encode("KYC verification process")
    assert len(result) == 384


def test_encode_normalized_vector_has_unit_norm():
    import math
    enc = SentenceTransformerEncoder()
    vec = enc.encode("joint account holder")
    norm = math.sqrt(sum(v * v for v in vec.values()))
    assert abs(norm - 1.0) < 1e-5


# ---------------------------------------------------------------------------
# Semantic quality: similar texts must score higher than dissimilar ones
# ---------------------------------------------------------------------------

def _cosine(a: dict, b: dict) -> float:
    import math
    dot = sum(a[k] * b.get(k, 0.0) for k in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def test_similar_banking_terms_score_higher_than_unrelated():
    enc = SentenceTransformerEncoder()
    a = enc.encode("retail customer")
    b = enc.encode("personal banking client")   # semantically close
    c = enc.encode("loan repayment schedule")   # unrelated domain

    sim_ab = _cosine(dict(a), dict(b))
    sim_ac = _cosine(dict(a), dict(c))
    assert sim_ab > sim_ac, (
        f"expected similar pair ({sim_ab:.3f}) > dissimilar pair ({sim_ac:.3f})"
    )


def test_identical_text_scores_one():
    enc = SentenceTransformerEncoder()
    a = enc.encode("ATM withdrawal")
    sim = _cosine(dict(a), dict(a))
    assert abs(sim - 1.0) < 1e-5


# ---------------------------------------------------------------------------
# Caching behaviour
# ---------------------------------------------------------------------------

def test_encode_caches_results():
    enc = SentenceTransformerEncoder()
    r1 = enc.encode("premium retail customer")
    r2 = enc.encode("premium retail customer")
    assert r1 is r2  # exact same dict object from cache


def test_clear_cache_removes_entries():
    enc = SentenceTransformerEncoder()
    enc.encode("KYC process")
    assert len(enc._cache) == 1
    enc.clear_cache()
    assert len(enc._cache) == 0


# ---------------------------------------------------------------------------
# Error handling: missing dependency
# ---------------------------------------------------------------------------

def test_missing_sentence_transformers_raises_import_error(monkeypatch):
    import sys
    # Temporarily hide sentence_transformers from the import system
    original = sys.modules.pop("sentence_transformers", None)
    try:
        enc = SentenceTransformerEncoder()
        enc._model = None  # reset lazy state
        monkeypatch.setitem(sys.modules, "sentence_transformers", None)  # type: ignore[arg-type]
        with pytest.raises(ImportError, match="pip install sentence-transformers"):
            enc._get_model()
    finally:
        if original is not None:
            sys.modules["sentence_transformers"] = original
        else:
            sys.modules.pop("sentence_transformers", None)


# ---------------------------------------------------------------------------
# Plug-in: MappingAgent and TaxonomyAgent accept the encoder
# ---------------------------------------------------------------------------

def test_mapping_agent_accepts_sentence_transformer_encoder(base_ontology):
    from ontobridge.agents.mapping.agent import MappingAgent
    from ontobridge.agents.mapping.glossary import from_ontology
    from ontobridge.models import EnrichedTerm, HarvestRecord, SourceType, Tier, CandidateLabel, SourceRef

    enc = SentenceTransformerEncoder()
    glossary = from_ontology(base_ontology)
    agent = MappingAgent(glossary=glossary, encoder=enc)

    harvest = HarvestRecord(
        text="A retail customer with premium credit products.",
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="CreditPolicy.pdf"),
        tier=Tier.DOCUMENT,
    )
    term = EnrichedTerm.from_harvest(harvest)
    term.candidate_labels = [CandidateLabel(text="Premium retail customer", confidence=0.9)]
    term.definition = "A retail customer who holds premium credit products."

    result = agent.apply(term)
    assert result.match_result is not None


def test_taxonomy_agent_accepts_sentence_transformer_encoder(base_ontology):
    from ontobridge.agents.mapping.agent import MappingAgent
    from ontobridge.agents.mapping.glossary import from_ontology
    from ontobridge.agents.taxonomy.agent import TaxonomyAgent
    from ontobridge.models import EnrichedTerm, HarvestRecord, SourceType, Tier, CandidateLabel, SourceRef

    enc = SentenceTransformerEncoder()
    glossary = from_ontology(base_ontology)
    mapping_agent = MappingAgent(glossary=glossary, encoder=enc)
    taxonomy_agent = TaxonomyAgent(ontology=base_ontology, encoder=enc)

    harvest = HarvestRecord(
        text="A joint account shared by two holders.",
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="DepositsPolicy.pdf"),
        tier=Tier.DOCUMENT,
    )
    term = EnrichedTerm.from_harvest(harvest)
    term.candidate_labels = [CandidateLabel(text="Joint account holder", confidence=0.9)]
    term.definition = "A person who holds a joint account with another party at the bank."

    term = mapping_agent.apply(term)
    result = taxonomy_agent.apply(term)
    assert result.taxonomy_placement is not None
