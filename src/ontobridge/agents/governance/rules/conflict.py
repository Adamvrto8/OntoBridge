from __future__ import annotations

from difflib import SequenceMatcher

from ontobridge.agents.governance.models import Candidate, RuleFinding, Severity
from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.agents.governance.rules.base import Rule

DEFINITION_SIMILARITY_COMPATIBLE = 0.55
FIBO_DIVERGENCE_THRESHOLD = 0.55


def _definition_similarity(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    return SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


class Rule12FIBOMatchDivergent(Rule):
    rule_id = 12
    category = "Conflict"
    title = "FIBO match with materially divergent definition"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        match = candidate.fibo_match
        if match is None:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="Candidate has no FIBO match to compare.",
            )
        sim = _definition_similarity(candidate.definition, match.expected_definition)
        if sim is None:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=True, severity=Severity.WARN,
                action="warn_require_justification",
                message=(
                    f"Candidate references FIBO term <{match.uri}> but no FIBO definition "
                    f"was provided to verify alignment. Require steward justification; "
                    f"add skos:relatedMatch."
                ),
                suggestions={"skos:relatedMatch": [match.uri]},
            )
        if sim >= FIBO_DIVERGENCE_THRESHOLD:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message=(
                    f"Candidate definition aligns with FIBO definition "
                    f"(similarity={sim:.2f})."
                ),
            )
        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=True, severity=Severity.WARN,
            action="warn_require_justification",
            message=(
                f"Candidate matches FIBO term <{match.uri}> but definition diverges "
                f"materially (similarity={sim:.2f} < {FIBO_DIVERGENCE_THRESHOLD}). "
                f"Require justification; add skos:relatedMatch."
            ),
            suggestions={
                "skos:relatedMatch": [match.uri],
                "similarity": round(sim, 3),
            },
        )


class Rule13DeprecatedTermMatch(Rule):
    rule_id = 13
    category = "Conflict"
    title = "Match against a deprecated term"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        hits = ontology.find_deprecated_by_label(candidate.preferred_label)
        if not hits:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="No match against deprecated terms.",
            )
        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=True, severity=Severity.WARN,
            action="warn_require_override",
            message=(
                f"'{candidate.preferred_label}' matches a previously deprecated term. "
                f"Show deprecation reason; propose skos:historyNote; require explicit "
                f"override."
            ),
            suggestions={
                "deprecated_uris": [c.uri for c in hits],
                "skos:historyNote": "Reintroduced after prior deprecation; see referenced term.",
                "require_override": True,
            },
        )


class Rule14CrossDomainIncompatibleMatch(Rule):
    rule_id = 14
    category = "Conflict"
    title = "Same preferred label in another domain with incompatible definition"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        hits = ontology.find_by_pref_label(candidate.preferred_label)
        if hits is None:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="No same-prefLabel hit in any scheme.",
            )
        if hits.scheme == candidate.domain:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="Match is within the same domain — handled by Rule 1.",
            )
        sim = _definition_similarity(candidate.definition, hits.definition)
        if sim is not None and sim >= DEFINITION_SIMILARITY_COMPATIBLE:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="Cross-domain hit but definitions are compatible — see Rule 5.",
            )

        if not (candidate.domain or candidate.domain_code):
            severity = Severity.BLOCK
            action = "block_require_qualifier"
            msg = (
                f"'{candidate.preferred_label}' already exists in scheme "
                f"<{hits.scheme}> with an incompatible definition, and the candidate has "
                f"no domain qualifier — block creation, enforce domain prefix."
            )
        else:
            severity = Severity.WARN
            action = "enforce_prefix_add_scope_note"
            msg = (
                f"'{candidate.preferred_label}' already exists in scheme "
                f"<{hits.scheme}> with an incompatible definition. Enforce domain prefix "
                f"and add skos:scopeNote on both terms."
            )
        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=True, severity=severity,
            action=action,
            message=msg,
            suggestions={
                "conflicting_uri": hits.uri,
                "conflicting_scheme": hits.scheme,
                "skos:scopeNote": (
                    "Term carries domain-specific meaning; see conflicting concept "
                    "in another scheme for contrast."
                ),
                "definition_similarity": round(sim, 3) if sim is not None else None,
            },
        )
