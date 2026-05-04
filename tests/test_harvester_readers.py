from __future__ import annotations

import json
import csv

import pytest

from ontobridge.agents.harvester.readers.text import PlainTextReader
from ontobridge.agents.harvester.readers.catalog import CatalogReader
from ontobridge.agents.harvester.protocols import RawDocument
from ontobridge.models.enums import SourceType


# ---------------------------------------------------------------------------
# PlainTextReader
# ---------------------------------------------------------------------------

class TestPlainTextReader:
    def test_can_read_txt(self, tmp_path):
        f = tmp_path / "policy.txt"
        f.write_text("hello", encoding="utf-8")
        assert PlainTextReader().can_read(f)

    def test_cannot_read_pdf(self, tmp_path):
        assert not PlainTextReader().can_read("document.pdf")

    def test_returns_raw_documents(self, tmp_path):
        f = tmp_path / "policy.txt"
        f.write_text(
            "Retail Customer\n"
            "A natural person who holds retail banking products for personal use.\n\n"
            "Loan Account\n"
            "A credit facility extended to a customer under the terms of a loan agreement.",
            encoding="utf-8",
        )
        docs = PlainTextReader().read(f)
        assert len(docs) >= 2
        assert all(isinstance(d, RawDocument) for d in docs)

    def test_section_heading_is_captured(self, tmp_path):
        f = tmp_path / "policy.txt"
        f.write_text(
            "Credit Policy\n\n"
            "Retail customer means a natural person holding retail banking products.\n",
            encoding="utf-8",
        )
        docs = PlainTextReader().read(f)
        assert any(d.section == "Credit Policy" for d in docs)

    def test_blank_lines_split_paragraphs(self, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text("Para one text here.\n\nPara two text here.\n", encoding="utf-8")
        docs = PlainTextReader().read(f)
        assert len(docs) == 2

    def test_source_type_is_policy_doc(self):
        assert PlainTextReader().source_type == SourceType.POLICY_DOC

    def test_empty_file_returns_empty_list(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        assert PlainTextReader().read(f) == []


# ---------------------------------------------------------------------------
# CatalogReader — JSON
# ---------------------------------------------------------------------------

class TestCatalogReaderJson:
    def test_can_read_json(self, tmp_path):
        f = tmp_path / "catalog.json"
        f.write_text("[]", encoding="utf-8")
        assert CatalogReader().can_read(f)

    def test_source_type_is_catalog(self):
        assert CatalogReader().source_type == SourceType.CATALOG

    def test_reads_name_and_description(self, tmp_path):
        data = [
            {
                "name": "Retail Customer",
                "description": (
                    "A natural person who holds retail products at the bank "
                    "for personal use across all channels."
                ),
                "schema": "retail",
            }
        ]
        f = tmp_path / "catalog.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        docs = CatalogReader().read(f)
        assert len(docs) == 1
        assert "Retail Customer" in docs[0].text
        assert docs[0].section == "retail"

    def test_skips_rows_without_description(self, tmp_path):
        data = [
            {"name": "EmptyTerm", "description": ""},
            {"name": "ShortDesc", "description": "Too short."},
            {
                "name": "Good Term",
                "description": (
                    "A well-described term with enough words to pass "
                    "the minimum length threshold."
                ),
            },
        ]
        f = tmp_path / "c.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        docs = CatalogReader().read(f)
        assert len(docs) == 1

    def test_metadata_contains_all_row_fields(self, tmp_path):
        data = [
            {
                "name": "KYC Process",
                "description": (
                    "A verification process that evaluates customer identity "
                    "before onboarding to satisfy regulatory requirements."
                ),
                "owner": "compliance_team",
                "schema": "onboarding",
            }
        ]
        f = tmp_path / "c.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        docs = CatalogReader().read(f)
        assert docs[0].metadata.get("owner") == "compliance_team"

    def test_items_key_wrapper(self, tmp_path):
        data = {
            "items": [
                {
                    "name": "Loan Account",
                    "description": (
                        "A credit facility extended to a customer under the "
                        "terms of a loan agreement with fixed repayment schedule."
                    ),
                }
            ]
        }
        f = tmp_path / "c.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        docs = CatalogReader().read(f)
        assert len(docs) == 1


# ---------------------------------------------------------------------------
# CatalogReader — CSV
# ---------------------------------------------------------------------------

class TestCatalogReaderCsv:
    def test_can_read_csv(self):
        assert CatalogReader().can_read("export.csv")

    def test_reads_csv_rows(self, tmp_path):
        f = tmp_path / "catalog.csv"
        with f.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["name", "description", "schema"])
            writer.writeheader()
            writer.writerow({
                "name": "Premium Retail Customer",
                "description": (
                    "A retail customer who holds premium credit products with "
                    "the bank and uses concierge channels for high-touch service."
                ),
                "schema": "retail",
            })
        docs = CatalogReader().read(f)
        assert len(docs) == 1
        assert "Premium Retail Customer" in docs[0].text

    def test_alternative_field_names(self, tmp_path):
        f = tmp_path / "catalog.csv"
        with f.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["term_name", "definition"])
            writer.writeheader()
            writer.writerow({
                "term_name": "ATM Withdrawal",
                "definition": (
                    "A cash withdrawal operation that uses an ATM channel and "
                    "produces a transaction record on the customer account."
                ),
            })
        docs = CatalogReader().read(f)
        assert len(docs) == 1


# ---------------------------------------------------------------------------
# PdfReader — skip if pypdf not installed
# ---------------------------------------------------------------------------

def test_pdf_reader_can_read_pdf():
    pypdf = pytest.importorskip("pypdf", reason="pypdf not installed")
    from ontobridge.agents.harvester.readers.pdf import PdfReader
    assert PdfReader().can_read("document.pdf")
    assert not PdfReader().can_read("document.docx")


def test_pdf_reader_raises_without_pypdf(monkeypatch):
    import sys
    original = sys.modules.pop("pypdf", None)
    try:
        from ontobridge.agents.harvester.readers.pdf import PdfReader
        reader = PdfReader()
        monkeypatch.setitem(sys.modules, "pypdf", None)  # type: ignore[arg-type]
        with pytest.raises(ImportError, match="pypdf"):
            reader.read("some.pdf")
    finally:
        if original is not None:
            sys.modules["pypdf"] = original
        else:
            sys.modules.pop("pypdf", None)


# ---------------------------------------------------------------------------
# DocxReader — skip if python-docx not installed
# ---------------------------------------------------------------------------

def test_docx_reader_can_read_docx():
    pytest.importorskip("docx", reason="python-docx not installed")
    from ontobridge.agents.harvester.readers.docx import DocxReader
    assert DocxReader().can_read("policy.docx")
    assert not DocxReader().can_read("policy.txt")


def test_docx_reader_raises_without_python_docx(monkeypatch):
    import sys
    original = sys.modules.pop("docx", None)
    try:
        from ontobridge.agents.harvester.readers.docx import DocxReader
        reader = DocxReader()
        monkeypatch.setitem(sys.modules, "docx", None)  # type: ignore[arg-type]
        with pytest.raises(ImportError, match="python-docx"):
            reader.read("some.docx")
    finally:
        if original is not None:
            sys.modules["docx"] = original
        else:
            sys.modules.pop("docx", None)
