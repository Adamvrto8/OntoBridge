from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from ontobridge.agents.governance.models import (
    Candidate,
    GovResult,
    RuleFinding,
    Severity,
)
from ontobridge.agents.governance.ontology import OntologyIndex, load_ontology
from ontobridge.agents.governance.rules import Rule, default_rules


class GovernanceAgent:
    def __init__(
        self,
        ontology: OntologyIndex | str | Path,
        rules: list[Rule] | None = None,
    ):
        if isinstance(ontology, (str, Path)):
            self.ontology = load_ontology(ontology)
        else:
            self.ontology = ontology
        self.rules: list[Rule] = rules if rules is not None else default_rules()

    def evaluate(self, candidate: Candidate) -> GovResult:
        result = GovResult(candidate=candidate)
        skos_props: dict[str, list[str]] = defaultdict(list)

        for rule in self.rules:
            finding = rule.evaluate(candidate, self.ontology)
            result.findings.append(finding)
            if finding.triggered:
                self._merge_skos(finding, skos_props)
                if finding.severity is Severity.BLOCK:
                    result.blocking_flags.append(
                        f"R{finding.rule_id:02d}:{finding.action}"
                    )

        result.required_skos_properties = dict(skos_props)
        result.recommended_action = self._recommend_action(result)
        return result

    @staticmethod
    def _merge_skos(finding: RuleFinding, bucket: dict[str, list[str]]) -> None:
        for key, value in finding.suggestions.items():
            if not key.startswith("skos:"):
                continue
            if isinstance(value, list):
                bucket[key].extend(str(v) for v in value)
            else:
                bucket[key].append(str(value))

    @staticmethod
    def _recommend_action(result: GovResult) -> str:
        if result.blocking_flags:
            return "block"
        triggered = result.triggered
        if any(
            f.action in {"flag_draft_enrich", "mark_draft_awaiting_source"}
            for f in triggered
        ):
            return "draft"
        if any(f.severity is Severity.WARN for f in triggered):
            return "review"
        return "publish"
