from __future__ import annotations

from dataclasses import dataclass

from ontobridge.agents.governance.ontology import OntologyIndex
from ontobridge.dashboard.config import DashboardConfig
from ontobridge.publisher.base import TermPublisher


@dataclass
class DashboardContext:
    publisher: TermPublisher
    ontology: OntologyIndex
    config: DashboardConfig
