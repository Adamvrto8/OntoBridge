from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from ontobridge.agents.governance.models import Candidate, RuleFinding
from ontobridge.agents.governance.ontology import OntologyIndex


class Rule(ABC):
    rule_id: ClassVar[int]
    category: ClassVar[str]
    title: ClassVar[str]

    @abstractmethod
    def evaluate(self, candidate: Candidate, ontology: OntologyIndex) -> RuleFinding:
        ...
