from __future__ import annotations

import csv
import io

import pytest

from ontobridge.export import export_glossary_csv, _term_to_csv_row
from ontobridge.models import LifecycleStatus
from ontobridge.models.enrichment import CandidateLabel, EnrichedTerm, TaxonomyPlacement
from ontobridge.models.enums import PlacementStatus, SourceType
from ontobridge.models.published import PublishedTerm
from ontobridge.models.source import HarvestRecord, SourceRef
from ontobridge.publisher import InMemoryPublisher

_NS = "http://ontobridge.dev/ontology/bank/"
_SCHEME = f"{_NS}LoanScheme"


def _make_published(
    uri: str,
    label: str,
    definition: str = "A definition.",
    alt_labels: list[str] | None = None,
    scheme_uri: str | None = None,
    approved_by: str = "alice",
) -> PublishedTerm:
    record = HarvestRecord(
        text=definition,
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="doc1"),
    )
    candidates = [CandidateLabel(text=label, confidence=1.0)]
    if alt_labels:
        candidates += [CandidateLabel(text=a, confidence=0.8) for a in alt_labels]
    enriched = EnrichedTerm(
        harvest_record=record,
        candidate_labels=candidates,
        definition=definition,
    )
    if scheme_uri:
        enriched.taxonomy_placement = TaxonomyPlacement(
            broader_concept_uri=f"{_NS}Loan",
            scheme_uri=scheme_uri,
            status=PlacementStatus.PLACED,
        )
    return PublishedTerm(
        enriched_term=enriched,
        term_uri=uri,
        lifecycle_status=LifecycleStatus.PUBLISHED,
        approved_by=approved_by,
    )


def _parse_csv(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


# ---------------------------------------------------------------------------
# _term_to_csv_row
# ---------------------------------------------------------------------------

def test_row_includes_all_columns():
    term = _make_published(f"{_NS}Mortgage", "Mortgage", scheme_uri=_SCHEME)
    row = _term_to_csv_row(term)
    assert set(row.keys()) == {"label", "definition", "alt_labels", "scheme", "status", "approved_by", "term_uri"}


def test_row_label_and_definition():
    term = _make_published(f"{_NS}Mortgage", "Mortgage", definition="A loan secured by property.")
    row = _term_to_csv_row(term)
    assert row["label"] == "Mortgage"
    assert row["definition"] == "A loan secured by property."


def test_row_alt_labels_semicolon_separated():
    term = _make_published(f"{_NS}Mortgage", "Mortgage", alt_labels=["Home loan", "Property loan"])
    row = _term_to_csv_row(term)
    assert "Home loan" in row["alt_labels"]
    assert "Property loan" in row["alt_labels"]
    assert "; " in row["alt_labels"]


def test_row_scheme_extracted_from_uri():
    term = _make_published(f"{_NS}Mortgage", "Mortgage", scheme_uri=_SCHEME)
    row = _term_to_csv_row(term)
    assert row["scheme"] == "LoanScheme"


def test_row_scheme_empty_when_no_placement():
    term = _make_published(f"{_NS}Mortgage", "Mortgage")
    row = _term_to_csv_row(term)
    assert row["scheme"] == ""


def test_row_approved_by():
    term = _make_published(f"{_NS}Mortgage", "Mortgage", approved_by="bob")
    row = _term_to_csv_row(term)
    assert row["approved_by"] == "bob"


def test_row_term_uri():
    uri = f"{_NS}Mortgage"
    term = _make_published(uri, "Mortgage")
    assert _term_to_csv_row(term)["term_uri"] == uri


# ---------------------------------------------------------------------------
# export_glossary_csv
# ---------------------------------------------------------------------------

def _publisher_with(*terms: PublishedTerm) -> InMemoryPublisher:
    pub = InMemoryPublisher()
    for t in terms:
        pub.create_term(t)
    return pub


def test_export_empty_publisher_returns_header_only():
    pub = InMemoryPublisher()
    csv_text = export_glossary_csv(pub)
    rows = _parse_csv(csv_text)
    assert rows == []
    assert "label" in csv_text  # header present


def test_export_one_term():
    pub = _publisher_with(_make_published(f"{_NS}Mortgage", "Mortgage"))
    rows = _parse_csv(export_glossary_csv(pub))
    assert len(rows) == 1
    assert rows[0]["label"] == "Mortgage"


def test_export_sorted_alphabetically():
    pub = _publisher_with(
        _make_published(f"{_NS}LTV", "LTV"),
        _make_published(f"{_NS}Mortgage", "Mortgage"),
        _make_published(f"{_NS}Collateral", "Collateral"),
    )
    rows = _parse_csv(export_glossary_csv(pub))
    labels = [r["label"] for r in rows]
    assert labels == sorted(labels, key=str.lower)


def test_export_only_published_by_default():
    from ontobridge.models.enrichment import EnrichedTerm
    published = _make_published(f"{_NS}Mortgage", "Mortgage")
    record = HarvestRecord(
        text="A definition.",
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="doc1"),
    )
    candidate = PublishedTerm(
        enriched_term=EnrichedTerm(
            harvest_record=record,
            candidate_labels=[CandidateLabel(text="LTV", confidence=1.0)],
            definition="A ratio.",
        ),
        term_uri=f"{_NS}LTV",
        lifecycle_status=LifecycleStatus.CANDIDATE,
    )
    pub = _publisher_with(published, candidate)
    rows = _parse_csv(export_glossary_csv(pub))
    assert len(rows) == 1
    assert rows[0]["label"] == "Mortgage"


def test_export_custom_statuses():
    published = _make_published(f"{_NS}Mortgage", "Mortgage")
    record = HarvestRecord(
        text="A ratio.",
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="doc1"),
    )
    draft = PublishedTerm(
        enriched_term=EnrichedTerm(
            harvest_record=record,
            candidate_labels=[CandidateLabel(text="LTV", confidence=1.0)],
            definition="A ratio.",
        ),
        term_uri=f"{_NS}LTV",
        lifecycle_status=LifecycleStatus.DRAFT,
    )
    pub = _publisher_with(published, draft)
    rows = _parse_csv(
        export_glossary_csv(pub, statuses={LifecycleStatus.PUBLISHED, LifecycleStatus.DRAFT})
    )
    assert len(rows) == 2


def test_export_is_valid_csv():
    pub = _publisher_with(
        _make_published(f"{_NS}Mortgage", "Mortgage", definition='Definition with "quotes" and, commas.')
    )
    csv_text = export_glossary_csv(pub)
    rows = _parse_csv(csv_text)
    assert rows[0]["definition"] == 'Definition with "quotes" and, commas.'
