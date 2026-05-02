from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ontobridge.models import (
    HarvestRecord,
    SourceRef,
    SourceType,
    Tier,
    to_jsonable,
)


def _ref() -> SourceRef:
    return SourceRef(
        source_system="unity_catalog",
        document_id="catalog.bronze.customers",
        section="column:customer_id",
        uri="uc://catalog.bronze.customers#customer_id",
    )


# ---- construction & validation ----

def test_harvest_record_builds_with_required_fields():
    r = HarvestRecord(
        text="A retail customer holds banking products.",
        source_type=SourceType.CATALOG,
        source_ref=_ref(),
        tier=Tier.STRUCTURED,
    )
    assert r.text.startswith("A retail")
    assert r.source_type is SourceType.CATALOG
    assert isinstance(r.timestamp, datetime)
    assert r.timestamp.tzinfo is not None


def test_harvest_record_rejects_empty_text():
    with pytest.raises(ValueError, match="text"):
        HarvestRecord(
            text="   ",
            source_type=SourceType.CATALOG,
            source_ref=_ref(),
        )


@pytest.mark.parametrize("bad", [-0.01, 1.01, 2.0, -5.0])
def test_harvest_record_rejects_invalid_confidence(bad):
    with pytest.raises(ValueError, match="confidence"):
        HarvestRecord(
            text="some text",
            source_type=SourceType.CATALOG,
            source_ref=_ref(),
            confidence=bad,
        )


def test_harvest_record_accepts_boundary_confidences():
    for c in (0.0, 1.0):
        r = HarvestRecord(
            text="x",
            source_type=SourceType.CATALOG,
            source_ref=_ref(),
            confidence=c,
        )
        assert r.confidence == c


def test_source_ref_rejects_empty_source_system():
    with pytest.raises(ValueError, match="source_system"):
        SourceRef(source_system="")


def test_harvest_record_requires_enum_types():
    with pytest.raises(TypeError, match="source_type"):
        HarvestRecord(
            text="x",
            source_type="catalog",  # type: ignore[arg-type]
            source_ref=_ref(),
        )
    with pytest.raises(TypeError, match="tier"):
        HarvestRecord(
            text="x",
            source_type=SourceType.CATALOG,
            source_ref=_ref(),
            tier="structured",  # type: ignore[arg-type]
        )


# ---- record_id ----

def test_record_id_is_deterministic_for_same_input():
    a = HarvestRecord(
        text="Loan application policy",
        source_type=SourceType.POLICY_DOC,
        source_ref=_ref(),
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    b = HarvestRecord(
        text="Loan application policy",
        source_type=SourceType.POLICY_DOC,
        source_ref=_ref(),
        timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    assert a.record_id == b.record_id


def test_record_id_differs_when_text_differs():
    base = dict(source_type=SourceType.POLICY_DOC, source_ref=_ref())
    a = HarvestRecord(text="loan", **base)
    b = HarvestRecord(text="deposit", **base)
    assert a.record_id != b.record_id


def test_record_id_can_be_overridden():
    r = HarvestRecord(
        text="x",
        source_type=SourceType.CATALOG,
        source_ref=_ref(),
        record_id="manual-id",
    )
    assert r.record_id == "manual-id"


# ---- serialization ----

def test_harvest_record_round_trips_via_to_jsonable():
    r = HarvestRecord(
        text="Retail PI customer",
        source_type=SourceType.USER_INPUT,
        source_ref=_ref(),
        confidence=0.9,
        tier=Tier.UNSTRUCTURED,
        metadata={"submitted_by": "alice"},
    )
    d = to_jsonable(r)
    assert d["source_type"] == "user_input"
    assert d["tier"] == "unstructured"
    assert d["confidence"] == 0.9
    assert d["metadata"] == {"submitted_by": "alice"}
    assert d["source_ref"]["source_system"] == "unity_catalog"
    assert isinstance(d["timestamp"], str)  # isoformat

    rebuilt = HarvestRecord(
        text=d["text"],
        source_type=SourceType(d["source_type"]),
        source_ref=SourceRef(**d["source_ref"]),
        confidence=d["confidence"],
        tier=Tier(d["tier"]),
        metadata=dict(d["metadata"]),
        record_id=d["record_id"],
    )
    assert rebuilt.record_id == r.record_id
    assert rebuilt.source_type is SourceType.USER_INPUT
