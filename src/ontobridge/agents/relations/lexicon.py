from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ontobridge.agents.governance.ontology import ObjectPropertyPair, OntologyIndex


class LookupDirection(str, Enum):
    FORWARD = "forward"
    INVERSE = "inverse"


@dataclass(frozen=True)
class LexiconLookup:
    pair: ObjectPropertyPair
    direction: LookupDirection

    @property
    def predicate_uri(self) -> str:
        if self.direction is LookupDirection.FORWARD:
            return self.pair.forward_uri
        return self.pair.inverse_uri

    @property
    def inverse_predicate_uri(self) -> str:
        if self.direction is LookupDirection.FORWARD:
            return self.pair.inverse_uri
        return self.pair.forward_uri


def _verb_forms(label: str) -> set[str]:
    """Generate a small set of surface forms for a verb label.
    e.g. 'holds' -> {'holds', 'hold'}, 'held by' -> {'held by', 'is held by'}.
    """
    base = label.casefold().strip()
    forms: set[str] = {base}
    # strip trailing -s for present singular -> infinitive (holds -> hold)
    if base.endswith("s") and not base.endswith("ss") and len(base) > 2:
        forms.add(base[:-1])
    # for inverse 'X by' forms, also add 'is X by'
    if base.endswith(" by"):
        forms.add(f"is {base}")
    return forms


class InverseVerbLexicon:
    def __init__(self, pairs: list[ObjectPropertyPair]):
        self._pairs: list[ObjectPropertyPair] = list(pairs)
        self._index: dict[str, LexiconLookup] = {}
        self._build_index()

    @classmethod
    def from_ontology(cls, ontology: OntologyIndex) -> "InverseVerbLexicon":
        return cls(ontology.object_property_pairs())

    def _build_index(self) -> None:
        for pair in self._pairs:
            for form in _verb_forms(pair.forward_label):
                self._index[form] = LexiconLookup(pair, LookupDirection.FORWARD)
            for form in _verb_forms(pair.inverse_label):
                self._index[form] = LexiconLookup(pair, LookupDirection.INVERSE)

    @property
    def pairs(self) -> list[ObjectPropertyPair]:
        return list(self._pairs)

    def known_forward_verbs(self) -> set[str]:
        return {form for pair in self._pairs for form in _verb_forms(pair.forward_label)}

    def lookup(self, verb: str) -> LexiconLookup | None:
        return self._index.get(verb.casefold().strip())

    def __contains__(self, verb: str) -> bool:
        return self.lookup(verb) is not None
