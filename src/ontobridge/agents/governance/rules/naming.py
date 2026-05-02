from __future__ import annotations

import re
from difflib import SequenceMatcher

from ontobridge.agents.governance.models import Candidate, RuleFinding, Severity
from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.agents.governance.rules.base import Rule

DEFINITION_SIMILARITY_COMPATIBLE = 0.55


def _slug_domain(domain: str | None, domain_code: str | None) -> str | None:
    if domain_code:
        return domain_code
    if not domain:
        return None
    return re.sub(r"[^A-Za-z0-9]+", "_", domain).strip("_") or None


def _definition_similarity(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    return SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


class Rule04UserRejectedSynonym(Rule):
    rule_id = 4
    category = "Naming"
    title = "User rejected synonym proposal"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        if not candidate.user_rejected_synonym:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="No prior synonym proposal was rejected by the user.",
            )
        prefix = _slug_domain(candidate.domain, candidate.domain_code)
        if prefix is None:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=True, severity=Severity.BLOCK,
                action="require_domain",
                message=(
                    "Synonym was rejected but candidate has no domain — cannot apply "
                    "domain-prefix naming rule."
                ),
            )
        new_label = f"{prefix}.{candidate.preferred_label}"
        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=True, severity=Severity.WARN,
            action="create_with_domain_prefix",
            message=(
                f"Synonym proposal was rejected — create a new term with domain prefix: "
                f"'{new_label}'."
            ),
            suggestions={
                "skos:prefLabel": new_label,
                "domain_prefix": prefix,
                "original_label": candidate.preferred_label,
            },
        )


class Rule05CrossDomainCompatibleMatch(Rule):
    rule_id = 5
    category = "Naming"
    title = "Same term in another domain (compatible meaning)"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        same_label = ontology.find_by_any_label(candidate.preferred_label)
        cross_domain = [
            c for c in same_label
            if c.scheme is not None and c.scheme != candidate.domain
        ]
        if not cross_domain:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="No same-label concept in another domain.",
            )

        compatible: list[tuple[str, str, str | None]] = []
        for c in cross_domain:
            sim = _definition_similarity(candidate.definition, c.definition)
            if sim is None or sim >= DEFINITION_SIMILARITY_COMPATIBLE:
                compatible.append((c.uri, c.scheme_label or c.scheme or "", c.definition))

        if not compatible:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="Same-label hit found, but definitions diverge — see Rule 14.",
            )

        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=True, severity=Severity.WARN,
            action="propose_skos_match",
            message=(
                f"'{candidate.preferred_label}' already exists in another domain with a "
                f"compatible definition — propose skos:exactMatch / skos:broadMatch "
                f"rather than duplicating."
            ),
            suggestions={
                "candidates": [
                    {"uri": u, "domain": d, "definition": defn}
                    for u, d, defn in compatible
                ],
                "proposed_property": "skos:exactMatch",
            },
        )


class Rule06UppercaseShortNoContext(Rule):
    rule_id = 6
    category = "Naming"
    title = "All-uppercase short label without context"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        label = candidate.preferred_label
        is_short_upper = (
            label.isupper()
            and len(label) <= 5
            and " " not in label
            and label.replace(".", "").isalpha()
        )
        if not is_short_upper:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="Label is not an uncontextualised short uppercase token.",
            )
        if candidate.acronym_expansion or (candidate.definition and len(candidate.definition.split()) >= 5):
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="Short uppercase label has expansion or definition context.",
            )
        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=True, severity=Severity.BLOCK,
            action="reject_require_expansion",
            message=(
                f"'{label}' is a short uppercase token with no expansion or definition. "
                f"Provide the full expansion as the preferred label before proceeding."
            ),
        )


class Rule07SingleNounNoQualifier(Rule):
    rule_id = 7
    category = "Naming"
    title = "Single common noun without domain qualifier"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        label = candidate.preferred_label.strip()
        is_single_word = " " not in label and "." not in label and "_" not in label
        is_lowercase_or_title = not label.isupper()
        if not (is_single_word and is_lowercase_or_title):
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="Label is multi-word or qualified.",
            )
        if candidate.domain or candidate.domain_code:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="Single-word label is bound to a domain scheme.",
            )
        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=True, severity=Severity.BLOCK,
            action="require_domain_qualifier",
            message=(
                f"'{label}' is a single common noun without a domain qualifier. "
                f"Add a domain (skos:inScheme) or rename with a qualifier before creation."
            ),
        )
