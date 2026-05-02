from __future__ import annotations

from ontobridge.agents.governance import (
    Candidate,
    GovernanceAgent,
    PolicyRef,
)

PARTY_SCHEME = "http://ontobridge.dev/ontology/bank/SchemeParty"
PROCESS_SCHEME = "http://ontobridge.dev/ontology/bank/SchemeProcess"


def test_clean_candidate_is_recommended_for_publish(base_ontology):
    agent = GovernanceAgent(base_ontology)
    cand = Candidate(
        preferred_label="Standing order mandate",
        domain=PROCESS_SCHEME,
        definition=(
            "A recurring payment instruction issued by a customer authorising the bank "
            "to debit a fixed amount on a defined schedule."
        ),
        policy_refs=[PolicyRef(document="CreditPolicy_v3.pdf", section="3.2")],
    )
    result = agent.evaluate(cand)
    assert result.recommended_action == "publish"
    assert result.blocking_flags == []
    assert result.triggered == []


def test_duplicate_label_blocks(base_ontology):
    agent = GovernanceAgent(base_ontology)
    cand = Candidate(
        preferred_label="Retail customer",
        domain=PARTY_SCHEME,
        definition=(
            "A natural person who holds retail banking products for personal or "
            "household use, served through the retail channel."
        ),
        policy_refs=[PolicyRef(document="CreditPolicy_v3.pdf")],
    )
    result = agent.evaluate(cand)
    assert result.recommended_action == "block"
    assert any(flag.startswith("R01:") for flag in result.blocking_flags)


def test_short_definition_yields_draft(base_ontology):
    agent = GovernanceAgent(base_ontology)
    cand = Candidate(
        preferred_label="Frequent flyer status",
        domain=PARTY_SCHEME,
        definition="Short.",
        policy_refs=[PolicyRef(document="CreditPolicy_v3.pdf")],
    )
    result = agent.evaluate(cand)
    # Rule 8 raises BLOCK severity which feeds blocking_flags first.
    assert result.recommended_action == "block"
    finding = result.by_rule(8)
    assert finding is not None and finding.triggered


def test_missing_policy_marks_draft_status(base_ontology):
    agent = GovernanceAgent(base_ontology)
    cand = Candidate(
        preferred_label="Retail PI premium customer",
        domain=PARTY_SCHEME,
        definition=(
            "A retail PI customer who maintains a premium product portfolio with the "
            "bank and qualifies for relationship-tier pricing on instalment products."
        ),
        policy_refs=[],
    )
    result = agent.evaluate(cand)
    finding = result.by_rule(10)
    assert finding is not None and finding.triggered
    assert "R10:mark_draft_awaiting_source" in result.blocking_flags


def test_fuzzy_only_match_yields_review(base_ontology):
    agent = GovernanceAgent(base_ontology)
    cand = Candidate(
        preferred_label="Retail custmer",  # typo of "Retail customer"
        domain=PARTY_SCHEME,
        definition=(
            "A natural person who holds retail banking products for personal use "
            "via digital and branch channels in the bank."
        ),
        policy_refs=[PolicyRef(document="CreditPolicy_v3.pdf")],
    )
    result = agent.evaluate(cand)
    assert result.recommended_action == "review"
    assert result.by_rule(3).triggered


def test_required_skos_properties_are_aggregated(base_ontology):
    agent = GovernanceAgent(base_ontology)
    cand = Candidate(
        preferred_label="Retail customer",
        domain=PARTY_SCHEME,
        definition=(
            "A natural person who holds retail banking products for personal use "
            "across multiple bank channels."
        ),
        policy_refs=[PolicyRef(document="CreditPolicy_v3.pdf")],
    )
    result = agent.evaluate(cand)
    assert "skos:altLabel" in result.required_skos_properties
    assert "Retail customer" in result.required_skos_properties["skos:altLabel"]


def test_all_14_rules_are_evaluated(base_ontology):
    agent = GovernanceAgent(base_ontology)
    cand = Candidate(preferred_label="Anything")
    result = agent.evaluate(cand)
    assert len(result.findings) == 14
    rule_ids = sorted(f.rule_id for f in result.findings)
    assert rule_ids == list(range(1, 15))
