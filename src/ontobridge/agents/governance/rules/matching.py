from __future__ import annotations

from difflib import SequenceMatcher

from ontobridge.agents.governance.models import Candidate, RuleFinding, Severity
from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.agents.governance.rules.base import Rule

FUZZY_THRESHOLD = 0.80


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


class Rule01ExactPrefLabelMatch(Rule):
    rule_id = 1
    category = "Matching"
    title = "Exact preferred label match"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        existing = ontology.find_by_pref_label(candidate.preferred_label)
        if existing is None:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="No existing concept with this preferred label.",
            )
        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=True, severity=Severity.BLOCK,
            action="block_propose_alt_label",
            message=(
                f"Term '{candidate.preferred_label}' duplicates the preferred label "
                f"of existing concept <{existing.uri}>. Add as skos:altLabel instead."
            ),
            suggestions={
                "target_uri": existing.uri,
                "target_pref_label": existing.pref_label,
                "skos:altLabel": [candidate.preferred_label],
            },
        )


class Rule02AcronymExpansionMatch(Rule):
    rule_id = 2
    category = "Matching"
    title = "Acronym expansion match"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        label = candidate.preferred_label
        is_acronym = label.isupper() and 2 <= len(label) <= 6 and " " not in label
        target = None
        match_kind = None

        if candidate.acronym_expansion:
            target = ontology.find_by_pref_label(candidate.acronym_expansion)
            if target is not None:
                match_kind = "explicit_expansion"
        if target is None and is_acronym:
            matches = ontology.find_by_acronym(label)
            if matches:
                target = matches[0]
                match_kind = "derived_initials"

        if target is None:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="No acronym/expansion match against existing concepts.",
            )

        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=True, severity=Severity.BLOCK,
            action="propose_reuse",
            message=(
                f"Acronym/expansion of '{label}' matches existing concept "
                f"'{target.pref_label}' (<{target.uri}>). Reuse it: keep full form as "
                f"skos:prefLabel and add the acronym as skos:altLabel."
            ),
            suggestions={
                "target_uri": target.uri,
                "match_kind": match_kind,
                "skos:prefLabel": target.pref_label,
                "skos:altLabel": [label] if is_acronym else [],
            },
        )


class Rule03FuzzyLabelMatch(Rule):
    rule_id = 3
    category = "Matching"
    title = "Fuzzy label similarity >= 80%"

    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        label = candidate.preferred_label
        ranked: list[tuple[str, str, float, str]] = []
        for c in ontology.concepts:
            score = _similarity(label, c.pref_label)
            if score >= FUZZY_THRESHOLD and score < 1.0:
                ranked.append((c.uri, c.pref_label, score, "prefLabel"))
            for alt in c.alt_labels:
                s = _similarity(label, alt)
                if s >= FUZZY_THRESHOLD and s < 1.0:
                    ranked.append((c.uri, alt, s, "altLabel"))

        if not ranked:
            return RuleFinding(
                self.rule_id, self.category, self.title,
                triggered=False, severity=Severity.INFO,
                action="none",
                message="No fuzzy matches above the 0.80 similarity threshold.",
            )

        ranked.sort(key=lambda t: t[2], reverse=True)
        top = ranked[:5]
        return RuleFinding(
            self.rule_id, self.category, self.title,
            triggered=True, severity=Severity.WARN,
            action="show_ranked_suggestions",
            message=(
                f"'{label}' has {len(ranked)} fuzzy match(es) >= "
                f"{int(FUZZY_THRESHOLD * 100)}% — review before creating."
            ),
            suggestions={
                "candidates": [
                    {"uri": uri, "label": lbl, "score": round(s, 3), "label_type": kind}
                    for uri, lbl, s, kind in top
                ],
            },
        )
