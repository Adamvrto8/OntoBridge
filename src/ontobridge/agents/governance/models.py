from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ontobridge.models.fibo import FIBOMatch


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    BLOCK = "block"


@dataclass
class PolicyRef:
    document: str
    section: str | None = None
    snippet: str | None = None


@dataclass
class Candidate:
    preferred_label: str
    alt_labels: list[str] = field(default_factory=list)
    definition: str | None = None
    domain: str | None = None
    domain_code: str | None = None
    policy_refs: list[PolicyRef] = field(default_factory=list)
    acronym_expansion: str | None = None
    fibo_match: FIBOMatch | None = None
    user_rejected_synonym: bool = False
    submitted_by: str | None = None


@dataclass
class RuleFinding:
    rule_id: int
    category: str
    title: str
    triggered: bool
    severity: Severity
    action: str
    message: str
    suggestions: dict[str, Any] = field(default_factory=dict)


@dataclass
class GovResult:
    candidate: Candidate
    findings: list[RuleFinding] = field(default_factory=list)
    recommended_action: str = "publish"
    blocking_flags: list[str] = field(default_factory=list)
    required_skos_properties: dict[str, list[str]] = field(default_factory=dict)

    @property
    def triggered(self) -> list[RuleFinding]:
        return [f for f in self.findings if f.triggered]

    def by_rule(self, rule_id: int) -> RuleFinding | None:
        for f in self.findings:
            if f.rule_id == rule_id:
                return f
        return None
