from __future__ import annotations

import json

import pytest

from ontobridge.agents.harvester.protocols import RawDocument
from ontobridge.agents.ner.backend import LLMBackend
from ontobridge.agents.ner.extractor import LLMNerExtractor
from ontobridge.agents.ner.prompt import (
    build_user_prompt,
    items_to_extracted_terms,
    parse_response,
)


# ---------------------------------------------------------------------------
# Mock backend
# ---------------------------------------------------------------------------

class MockBackend:
    """Returns a fixed JSON string, optionally raising on call."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.call_count = 0

    def complete(self, system: str, user: str) -> str:
        self.call_count += 1
        return self._response


def _backend(terms: list[dict]) -> MockBackend:
    return MockBackend(json.dumps(terms))


def _doc(text: str, section: str | None = None) -> RawDocument:
    return RawDocument(text=text, section=section)


# ---------------------------------------------------------------------------
# parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_valid_json_array(self):
        raw = '[{"term": "Loan", "definition": "A debt instrument.", "confidence": 0.9}]'
        result = parse_response(raw)
        assert len(result) == 1
        assert result[0]["term"] == "Loan"

    def test_empty_array(self):
        assert parse_response("[]") == []

    def test_malformed_json_returns_empty(self):
        assert parse_response("not json at all") == []

    def test_strips_markdown_fences(self):
        raw = "```json\n[{\"term\": \"Credit\", \"definition\": \"Short def.\", \"confidence\": 0.8}]\n```"
        result = parse_response(raw)
        assert len(result) == 1

    def test_strips_plain_fences(self):
        raw = "```[{\"term\": \"T\", \"definition\": \"D D D D D D D D D D.\", \"confidence\": 0.8}]```"
        result = parse_response(raw)
        assert len(result) == 1

    def test_json_preceded_by_sentence(self):
        raw = 'Here are the terms I found:\n[{"term": "X", "definition": "Y Y Y Y Y Y Y Y Y Y.", "confidence": 0.7}]'
        result = parse_response(raw)
        assert len(result) == 1

    def test_non_list_json_returns_empty(self):
        assert parse_response('{"term": "Loan"}') == []

    def test_multiple_terms(self):
        data = [
            {"term": "A", "definition": "Definition A.", "confidence": 0.9},
            {"term": "B", "definition": "Definition B.", "confidence": 0.8},
        ]
        result = parse_response(json.dumps(data))
        assert len(result) == 2


# ---------------------------------------------------------------------------
# items_to_extracted_terms
# ---------------------------------------------------------------------------

class TestItemsToExtractedTerms:
    def test_converts_valid_item(self):
        items = [{"term": "Credit Risk", "definition": "Risk of borrower default.", "confidence": 0.9}]
        terms = items_to_extracted_terms(items)
        assert len(terms) == 1
        assert terms[0].candidate_label == "Credit Risk"
        assert terms[0].confidence == 0.9

    def test_skips_missing_term(self):
        items = [{"definition": "Some definition here.", "confidence": 0.8}]
        assert items_to_extracted_terms(items) == []

    def test_skips_missing_definition(self):
        items = [{"term": "Loan", "confidence": 0.8}]
        assert items_to_extracted_terms(items) == []

    def test_skips_non_dict_entries(self):
        items = ["not a dict", {"term": "X", "definition": "Y Y Y Y Y Y Y Y Y Y.", "confidence": 0.8}]
        terms = items_to_extracted_terms(items)
        assert len(terms) == 1

    def test_clamps_confidence_above_1(self):
        items = [{"term": "T", "definition": "D D D D D D D D D D.", "confidence": 1.5}]
        terms = items_to_extracted_terms(items)
        assert terms[0].confidence == 1.0

    def test_clamps_confidence_below_0(self):
        items = [{"term": "T", "definition": "D D D D D D D D D D.", "confidence": -0.5}]
        terms = items_to_extracted_terms(items)
        assert terms[0].confidence == 0.0

    def test_defaults_confidence_on_bad_type(self):
        items = [{"term": "T", "definition": "D D D D D D D D D D.", "confidence": "high"}]
        terms = items_to_extracted_terms(items)
        assert terms[0].confidence == 0.8

    def test_empty_input(self):
        assert items_to_extracted_terms([]) == []


# ---------------------------------------------------------------------------
# build_user_prompt
# ---------------------------------------------------------------------------

def test_build_user_prompt_contains_text():
    prompt = build_user_prompt("A Retail PI Customer is a natural person.")
    assert "A Retail PI Customer is a natural person." in prompt


# ---------------------------------------------------------------------------
# LLMNerExtractor — constructor
# ---------------------------------------------------------------------------

def test_invalid_min_confidence():
    with pytest.raises(ValueError, match="min_confidence"):
        LLMNerExtractor(MockBackend("[]"), min_confidence=1.5)


def test_invalid_min_definition_words():
    with pytest.raises(ValueError, match="min_definition_words"):
        LLMNerExtractor(MockBackend("[]"), min_definition_words=-1)


def test_satisfies_llm_backend_protocol():
    assert isinstance(MockBackend("[]"), LLMBackend)


# ---------------------------------------------------------------------------
# LLMNerExtractor.extract — happy path
# ---------------------------------------------------------------------------

class TestExtract:
    def _extractor(self, terms: list[dict], **kwargs) -> LLMNerExtractor:
        return LLMNerExtractor(_backend(terms), **kwargs)

    def test_returns_extracted_terms(self):
        payload = [
            {
                "term": "Retail PI Customer",
                "definition": "A natural person holding a Personal Instalment loan product with the bank.",
                "confidence": 0.95,
            }
        ]
        extractor = self._extractor(payload)
        results = extractor.extract(_doc("A Retail PI Customer is a natural person holding a PI loan."))
        assert len(results) == 1
        assert results[0].candidate_label == "Retail PI Customer"
        assert results[0].confidence == 0.95

    def test_propagates_section_from_doc(self):
        payload = [
            {
                "term": "Credit Check",
                "definition": "A mandatory verification of a customer creditworthiness before loan approval.",
                "confidence": 0.90,
            }
        ]
        extractor = self._extractor(payload)
        results = extractor.extract(_doc("Credit Check is mandatory.", section="§2.1"))
        assert results[0].section == "§2.1"

    def test_propagates_metadata_from_doc(self):
        payload = [
            {
                "term": "Gross Income",
                "definition": "The total income of a customer before any deductions are applied by the bank.",
                "confidence": 0.85,
            }
        ]
        extractor = self._extractor(payload)
        doc = RawDocument(text="Gross Income is the primary criterion.", metadata={"page": 3})
        results = extractor.extract(doc)
        assert results[0].metadata == {"page": 3}

    def test_multiple_terms_returned(self):
        payload = [
            {"term": "Loan Application", "definition": "A formal request submitted by a customer to obtain a credit product from the bank.", "confidence": 0.91},
            {"term": "Credit Score", "definition": "A numerical representation of a customer creditworthiness assessed by the bank.", "confidence": 0.88},
        ]
        extractor = self._extractor(payload)
        results = extractor.extract(_doc("Some policy text about loans and scores."))
        assert len(results) == 2

    def test_empty_text_returns_empty(self):
        extractor = self._extractor([])
        assert extractor.extract(_doc("")) == []
        assert extractor.extract(_doc("   ")) == []

    def test_llm_not_called_for_empty_text(self):
        backend = MockBackend("[]")
        extractor = LLMNerExtractor(backend)
        extractor.extract(_doc(""))
        assert backend.call_count == 0

    def test_malformed_llm_response_returns_empty(self):
        extractor = LLMNerExtractor(MockBackend("not valid json"))
        result = extractor.extract(_doc("Some policy text paragraph here."))
        assert result == []

    def test_empty_llm_array_returns_empty(self):
        extractor = LLMNerExtractor(MockBackend("[]"))
        assert extractor.extract(_doc("Text without business terms.")) == []


# ---------------------------------------------------------------------------
# LLMNerExtractor.extract — filtering
# ---------------------------------------------------------------------------

class TestFiltering:
    def test_confidence_filter(self):
        payload = [
            {"term": "High", "definition": "A high confidence term from the policy document of the bank.", "confidence": 0.9},
            {"term": "Low", "definition": "A low confidence term from the policy document of the bank.", "confidence": 0.3},
        ]
        extractor = LLMNerExtractor(_backend(payload), min_confidence=0.5)
        results = extractor.extract(_doc("Some text."))
        assert len(results) == 1
        assert results[0].candidate_label == "High"

    def test_short_definition_filtered(self):
        payload = [
            {"term": "Short", "definition": "Too short.", "confidence": 0.9},
            {"term": "Long", "definition": "This definition is long enough to pass the minimum word count filter.", "confidence": 0.9},
        ]
        extractor = LLMNerExtractor(_backend(payload), min_definition_words=10)
        results = extractor.extract(_doc("Some text."))
        assert len(results) == 1
        assert results[0].candidate_label == "Long"

    def test_zero_min_confidence_accepts_all(self):
        payload = [
            {"term": "T", "definition": "A term definition with enough words to pass the filter here.", "confidence": 0.1},
        ]
        extractor = LLMNerExtractor(_backend(payload), min_confidence=0.0, min_definition_words=0)
        results = extractor.extract(_doc("Text."))
        assert len(results) == 1

    def test_zero_min_definition_words_accepts_short(self):
        payload = [
            {"term": "T", "definition": "Short.", "confidence": 0.9},
        ]
        extractor = LLMNerExtractor(_backend(payload), min_definition_words=0)
        results = extractor.extract(_doc("Text."))
        assert len(results) == 1
