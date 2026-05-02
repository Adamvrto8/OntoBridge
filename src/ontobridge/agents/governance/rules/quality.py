from __future__ import annotations

from ontobridge.agents.governance.models import Candidate, RuleFinding, Severity
from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.agents.governance.rules.base import Rule

MIN_DEFINITION_WORDS = 10


def _word_count(text: str | None) -> int:
    if not text:
        return 0
    return len([w for w in text.split() if w.strip()])


class Rule08DefinitionTooShort(Rule):
    rule_id = 8
    category = "Quality"
    title = "Definition shorter than 10 words"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        wc = _word_count(candidate.definition)
        if wc >= MIN_DEFINITION_WORDS:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message=f"Definition has {wc} words.",
            )
        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=True, severity=Severity.BLOCK,
            action="flag_draft_enrich",
            message=(
                f"Definition has {wc} word(s) (< {MIN_DEFINITION_WORDS}). "
                f"Flag as draft, trigger LLM enrichment, block publish."
            ),
            suggestions={
                "status": "draft",
                "trigger": "definition_enrichment",
                "block_publish": True,
            },
        )


class Rule09CircularDefinition(Rule):
    rule_id = 9
    category = "Quality"
    title = "Definition contains the preferred label (circular)"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        if not candidate.definition or not candidate.preferred_label:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="No definition to check.",
            )
        if candidate.preferred_label.casefold() in candidate.definition.casefold():
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=True, severity=Severity.BLOCK,
                action="block_publish_steward_review",
                message=(
                    f"Definition contains the preferred label '{candidate.preferred_label}' "
                    f"(circular). Block publish; flag for human steward."
                ),
                suggestions={
                    "highlight": candidate.preferred_label,
                    "block_publish": True,
                },
            )
        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=False, severity=Severity.INFO,
            action="none",
            message="Definition is non-circular.",
        )


class Rule10NoPolicySource(Rule):
    rule_id = 10
    category = "Quality"
    title = "No policy source linked"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        if candidate.policy_refs:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message=f"Linked to {len(candidate.policy_refs)} policy reference(s).",
            )
        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=True, severity=Severity.BLOCK,
            action="mark_draft_awaiting_source",
            message=(
                "No policy section was matched by the Policy Linker. Mark draft, "
                "provenance status 'awaiting source'; block promotion to published."
            ),
            suggestions={
                "status": "draft",
                "provenance_status": "awaiting source",
                "block_publish": True,
            },
        )


class Rule11MultiPolicySource(Rule):
    rule_id = 11
    category = "Quality"
    title = "Definition found in multiple policy documents"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        documents = {p.document for p in candidate.policy_refs if p.document}
        if len(documents) < 2:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message=f"{len(documents)} distinct source document(s).",
            )
        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=True, severity=Severity.WARN,
            action="multi_policy_steward_signoff",
            message=(
                f"Definition is sourced from {len(documents)} distinct policy documents. "
                f"Link all sources, mark multi-policy, require steward sign-off."
            ),
            suggestions={
                "documents": sorted(documents),
                "flag": "multi_policy",
                "require_steward_signoff": True,
            },
        )
