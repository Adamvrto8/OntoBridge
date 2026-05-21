from __future__ import annotations

import pytest

from ontobridge.agents.definition.extractor import HeuristicDefinitionExtractor
from ontobridge.agents.definition.agent import DefinitionAgent
from ontobridge.models.enums import SourceType
from ontobridge.models.source import HarvestRecord, SourceRef

_EXT = HeuristicDefinitionExtractor()


def _record(text: str) -> HarvestRecord:
    return HarvestRecord(
        text=text,
        source_type=SourceType.POLICY_DOC,
        source_ref=SourceRef(source_system="test", document_id="doc1"),
    )


# ---------------------------------------------------------------------------
# HeuristicDefinitionExtractor — basic cases
# ---------------------------------------------------------------------------

def test_single_sentence_returned_directly():
    text = "A mortgage is a loan secured by real property held as collateral."
    result = _EXT.extract(text)
    assert result == text


def test_empty_text_returns_none():
    assert _EXT.extract("") is None
    assert _EXT.extract("   ") is None


def test_too_short_single_sentence_returns_none():
    assert _EXT.extract("Short text.") is None


def test_picks_definition_sentence_over_procedural():
    text = (
        "Documentation must be submitted before closing. "
        "A mortgage is a loan secured by real property that the borrower repays over time. "
        "See also section 5 for exceptions."
    )
    result = _EXT.extract(text, label="mortgage")
    assert result is not None
    assert "loan secured" in result


def test_label_at_start_boosts_score():
    text = (
        "Please refer to the policy document for details. "
        "Mortgage is a financial product secured by real estate used to fund property purchases."
    )
    result = _EXT.extract(text, label="Mortgage")
    assert result is not None
    assert "Mortgage" in result


def test_definition_verb_boosts_score():
    text = (
        "Note that all terms apply. "
        "LTV refers to the ratio of the loan amount to the appraised value of the collateral property."
    )
    result = _EXT.extract(text, label="LTV")
    assert result is not None
    assert "ratio" in result


def test_fallback_to_first_adequate_sentence_when_no_high_score():
    text = (
        "This document covers all definitions. "
        "The bank maintains credit records for all customers to assess risk profiles accurately."
    )
    result = _EXT.extract(text)
    assert result is not None
    assert len(result.split()) >= 6


def test_colon_split_picks_body_as_definition():
    text = "KYC: A verification process that evaluates customer identity before onboarding."
    result = _EXT.extract(text, label="KYC")
    assert result is not None
    assert "verification" in result


def test_label_case_insensitive():
    text = (
        "Regulatory requirements apply. "
        "COLLATERAL is an asset pledged by a borrower to secure a loan obligation with the bank."
    )
    result = _EXT.extract(text, label="collateral")
    assert result is not None
    assert "asset" in result


def test_very_long_sentence_penalised_in_favour_of_shorter():
    long_sent = "A " + " ".join(["word"] * 65) + "."
    short_sent = "A mortgage is a loan secured by property used to fund real estate purchases."
    text = long_sent + " " + short_sent
    result = _EXT.extract(text, label="mortgage")
    assert result == short_sent


# ---------------------------------------------------------------------------
# DefinitionAgent — integration
# ---------------------------------------------------------------------------

def test_agent_returns_string_not_none():
    record = _record("A mortgage is a loan secured by real property for purchase financing.")
    agent = DefinitionAgent()
    result = agent.extract(record, label="mortgage")
    assert isinstance(result, str)
    assert result


def test_agent_falls_back_to_full_text_when_extractor_returns_none():
    short_text = "Too short."
    record = _record(short_text)
    agent = DefinitionAgent()
    result = agent.extract(record, label="x")
    assert result == short_text


def test_agent_uses_label_from_caller():
    record = _record(
        "This section covers compliance rules. "
        "KYC verification process is a mandatory identity check performed before customer onboarding."
    )
    agent = DefinitionAgent()
    result = agent.extract(record, label="KYC verification process")
    assert "identity check" in result


# ---------------------------------------------------------------------------
# Integration with HarvesterAgent
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# New pattern coverage: which-is, numbered lists, table rows
# ---------------------------------------------------------------------------

def test_which_is_recognised_as_definition_trigger():
    """'which is' should be treated as a definition verb and boost the score."""
    text = (
        "A loan is a financial arrangement for personal banking use. "
        "Anti-Money Laundering (AML), which is the process of detecting and "
        "reporting suspicious financial transactions in banking."
    )
    result = _EXT.extract(text, label="AML")
    assert result is not None
    assert "detecting" in result


def test_numbered_list_prefix_stripped():
    """'1. Term: Definition' — numbered prefix should not block colon extraction."""
    text = "1. Credit Risk: The probability of financial loss arising from a borrower's failure to repay."
    result = _EXT.extract(text, label="Credit Risk")
    assert result is not None
    assert "probability" in result


def test_table_row_markers_stripped():
    """Pipe markers from markdown/ASCII tables should not corrupt extraction."""
    text = "| AML | Anti-Money Laundering | The process of detecting and preventing illegal financial activity in banking. |"
    result = _EXT.extract(text, label="AML")
    assert result is not None
    assert "AML" in result or "detecting" in result


def test_harvester_uses_definition_agent(tmp_path):
    from ontobridge.agents.harvester.agent import HarvesterAgent

    doc = tmp_path / "policy.txt"
    doc.write_text(
        "Overdraft is a credit facility that allows customers to withdraw "
        "funds beyond their available account balance up to an agreed limit. "
        "See section 3 for fees."
    )
    harvester = HarvesterAgent()
    terms = harvester.harvest_terms(doc)
    for term in terms:
        assert term.definition is not None
        assert len(term.definition.split()) >= 6
        # Should not be the procedural sentence
        assert "See section" not in term.definition
