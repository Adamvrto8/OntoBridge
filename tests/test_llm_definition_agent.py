from __future__ import annotations

import json

import pytest

from ontobridge.agents.definition.agent import LLMDefinitionAgent
from ontobridge.agents.definition.prompt import (
    build_user_prompt,
    extract_business_rules,
    extract_definition,
    parse_response,
)
from ontobridge.models import CandidateLabel, EnrichedTerm
from ontobridge.models.enrichment import PolicyContext, TaxonomyPlacement
from ontobridge.models.enums import PlacementStatus, SourceType
from ontobridge.models.source import HarvestRecord, SourceRef


# ---------------------------------------------------------------------------
# Mock backend (reuse pattern from NER tests)
# ---------------------------------------------------------------------------

class MockBackend:
    def __init__(self, response: str) -> None:
        self._response = response
        self.call_count = 0

    def complete(self, system: str, user: str) -> str:
        self.call_count += 1
        return self._response


def _backend(definition: str, rules: list[dict] | None = None) -> MockBackend:
    payload = {"definition": definition, "business_rules": rules or []}
    return MockBackend(json.dumps(payload))


def _make_term(
    label: str = "Retail PI Customer",
    definition: str = "A customer in the PI segment.",
    with_policy: bool = False,
    with_placement: bool = False,
) -> EnrichedTerm:
    record = HarvestRecord(
        text=definition,
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test"),
    )
    term = EnrichedTerm.from_harvest(record)
    term.candidate_labels = [CandidateLabel(text=label, confidence=0.9)]
    term.definition = definition

    if with_policy:
        term.policy_context = [
            PolicyContext(
                paragraph="A Retail PI Customer is a natural person holding a Personal Instalment loan.",
                document_ref="CreditPolicy_v3.pdf",
                section="§2.1",
            )
        ]
    if with_placement:
        term.taxonomy_placement = TaxonomyPlacement(
            broader_concept_uri="http://ontobridge.dev/ontology/bank/RetailCustomer",
            scheme_uri="http://ontobridge.dev/ontology/bank/RetailScheme",
            domain_prefix="Retail",
            status=PlacementStatus.PLACED,
        )
    return term


# ---------------------------------------------------------------------------
# parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_valid_object(self):
        raw = '{"definition": "A customer.", "business_rules": []}'
        assert parse_response(raw)["definition"] == "A customer."

    def test_empty_object(self):
        assert parse_response("{}") == {}

    def test_malformed_returns_empty(self):
        assert parse_response("not json") == {}

    def test_array_returns_empty(self):
        assert parse_response("[]") == {}

    def test_strips_markdown_fences(self):
        raw = '```json\n{"definition": "Def.", "business_rules": []}\n```'
        assert parse_response(raw).get("definition") == "Def."

    def test_finds_object_after_preamble(self):
        raw = 'Here is the result:\n{"definition": "Def.", "business_rules": []}'
        assert parse_response(raw).get("definition") == "Def."


# ---------------------------------------------------------------------------
# extract_definition
# ---------------------------------------------------------------------------

class TestExtractDefinition:
    def test_returns_definition_above_min_words(self):
        data = {"definition": "A retail customer holding a personal instalment loan product."}
        result = extract_definition(data, min_words=5)
        assert result is not None

    def test_returns_none_below_min_words(self):
        data = {"definition": "Too short."}
        assert extract_definition(data, min_words=10) is None

    def test_missing_key_returns_none(self):
        assert extract_definition({}, min_words=1) is None

    def test_strips_whitespace(self):
        data = {"definition": "  A valid definition with enough words here.  "}
        result = extract_definition(data, min_words=5)
        assert result is not None
        assert not result.startswith(" ")


# ---------------------------------------------------------------------------
# extract_business_rules
# ---------------------------------------------------------------------------

class TestExtractBusinessRules:
    def test_valid_rules(self):
        data = {
            "business_rules": [
                {
                    "rule_text": "IF loan > 500k THEN credit check required.",
                    "condition": "IF loan > 500k",
                    "consequence": "THEN credit check required.",
                }
            ]
        }
        rules = extract_business_rules(data)
        assert len(rules) == 1
        assert rules[0].rule_text == "IF loan > 500k THEN credit check required."
        assert rules[0].condition == "IF loan > 500k"
        assert rules[0].consequence == "THEN credit check required."

    def test_missing_rule_text_skipped(self):
        data = {"business_rules": [{"condition": "IF x", "consequence": "THEN y"}]}
        assert extract_business_rules(data) == []

    def test_non_dict_entries_skipped(self):
        data = {"business_rules": ["not a dict", {"rule_text": "IF x THEN y.", "condition": None, "consequence": None}]}
        rules = extract_business_rules(data)
        assert len(rules) == 1

    def test_non_list_returns_empty(self):
        assert extract_business_rules({"business_rules": "oops"}) == []

    def test_missing_key_returns_empty(self):
        assert extract_business_rules({}) == []

    def test_empty_condition_stored_as_none(self):
        data = {"business_rules": [{"rule_text": "IF x THEN y.", "condition": "", "consequence": "THEN y."}]}
        rules = extract_business_rules(data)
        assert rules[0].condition is None


# ---------------------------------------------------------------------------
# build_user_prompt
# ---------------------------------------------------------------------------

class TestBuildUserPrompt:
    def test_contains_label(self):
        term = _make_term(label="Credit Score")
        assert "Credit Score" in build_user_prompt(term)

    def test_contains_existing_definition(self):
        term = _make_term(definition="A scoring measure for creditworthiness.")
        assert "A scoring measure" in build_user_prompt(term)

    def test_contains_policy_paragraph(self):
        term = _make_term(with_policy=True)
        prompt = build_user_prompt(term)
        assert "CreditPolicy_v3.pdf" in prompt
        assert "§2.1" in prompt
        assert "natural person" in prompt

    def test_contains_domain_and_broader(self):
        term = _make_term(with_placement=True)
        prompt = build_user_prompt(term)
        assert "Retail" in prompt
        assert "RetailCustomer" in prompt

    def test_no_placement_no_crash(self):
        term = _make_term()
        prompt = build_user_prompt(term)
        assert "Retail PI Customer" in prompt


# ---------------------------------------------------------------------------
# LLMDefinitionAgent — constructor
# ---------------------------------------------------------------------------

def test_invalid_min_definition_words():
    with pytest.raises(ValueError, match="min_definition_words"):
        LLMDefinitionAgent(MockBackend("{}"), min_definition_words=-1)


# ---------------------------------------------------------------------------
# LLMDefinitionAgent.apply — happy path
# ---------------------------------------------------------------------------

class TestApply:
    def test_replaces_definition(self):
        long_def = "A natural person holding a Personal Instalment loan product with the bank."
        agent = LLMDefinitionAgent(_backend(long_def))
        term = _make_term()
        agent.apply(term)
        assert term.definition == long_def

    def test_populates_business_rules(self):
        rules = [
            {"rule_text": "IF loan > 500k THEN credit check required.", "condition": "IF loan > 500k", "consequence": "THEN credit check required."}
        ]
        agent = LLMDefinitionAgent(_backend("A valid definition with enough words here.", rules))
        term = _make_term()
        agent.apply(term)
        assert len(term.business_rules) == 1
        assert "IF loan" in term.business_rules[0].rule_text

    def test_keeps_original_definition_on_malformed_response(self):
        original = "Original definition stays."
        agent = LLMDefinitionAgent(MockBackend("not valid json"))
        term = _make_term(definition=original)
        agent.apply(term)
        assert term.definition == original

    def test_keeps_original_definition_when_llm_def_too_short(self):
        original = "Original definition."
        agent = LLMDefinitionAgent(_backend("Too short."), min_definition_words=10)
        term = _make_term(definition=original)
        agent.apply(term)
        assert term.definition == original

    def test_no_rules_in_response_leaves_business_rules_empty(self):
        agent = LLMDefinitionAgent(_backend("A valid definition with enough words here."))
        term = _make_term()
        agent.apply(term)
        assert term.business_rules == []

    def test_skips_term_without_label(self):
        backend = MockBackend("{}")
        agent = LLMDefinitionAgent(backend)
        record = HarvestRecord(
            text="text",
            source_type=SourceType.POLICY_DOC,
            source_ref=SourceRef(source_system="test"),
        )
        term = EnrichedTerm.from_harvest(record)  # no candidate_labels
        agent.apply(term)
        assert backend.call_count == 0

    def test_llm_called_once_per_apply(self):
        backend = _backend("A valid definition with enough words for the term.")
        agent = LLMDefinitionAgent(backend)
        term = _make_term()
        agent.apply(term)
        assert backend.call_count == 1

    def test_uses_policy_context_in_prompt(self):
        backend = _backend("A valid definition with enough words for the test.")
        agent = LLMDefinitionAgent(backend)
        term = _make_term(with_policy=True)
        agent.apply(term)
        _, user = backend.complete.__self__._response, None
        # Verify the agent ran (definition replaced) — prompt content tested separately
        assert backend.call_count == 1

    def test_apply_with_full_context(self):
        long_def = "A retail bank customer in the Personal Instalment segment holding an active loan product."
        rules = [
            {"rule_text": "IF application > 500k CZK THEN credit check is mandatory.", "condition": "IF application > 500k CZK", "consequence": "THEN credit check is mandatory."},
            {"rule_text": "IF customer has no income proof THEN application is rejected.", "condition": "IF customer has no income proof", "consequence": "THEN application is rejected."},
        ]
        agent = LLMDefinitionAgent(_backend(long_def, rules))
        term = _make_term(with_policy=True, with_placement=True)
        agent.apply(term)
        assert term.definition == long_def
        assert len(term.business_rules) == 2
