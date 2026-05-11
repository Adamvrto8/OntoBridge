from __future__ import annotations

import re

from ontobridge.agents.fibo.loader import FiboIndex
from ontobridge.models.fibo import FIBOMatch

_FIBO_MODULE_RE = re.compile(
    r"https?://spec\.edmcouncil\.org/fibo/ontology/([A-Z]+)/", re.IGNORECASE
)


def _extract_module(uri: str) -> str | None:
    m = _FIBO_MODULE_RE.search(uri)
    return m.group(1).upper() if m else None



class FiboMatcher:
    def __init__(self, index: FiboIndex) -> None:
        self.index = index

    def match(self, label: str | None, definition: str | None = None) -> FIBOMatch | None:
        if not label or not label.strip():
            return None

        normalized = FiboIndex.normalize_label(label)
        uris = self.index.uri_by_label.get(normalized)
        if not uris:
            return None

        uri = sorted(uris)[0]
        expected_definition = self.index.uri_to_definition.get(uri)
        alt_labels = list(self.index.alt_labels_by_uri.get(uri, []))

        broader_uri   = self.index.parent_by_uri.get(uri)
        broader_label = self.index.label_by_uri.get(broader_uri) if broader_uri else None
        module        = _extract_module(uri)

        return FIBOMatch(
            uri=uri,
            expected_definition=expected_definition,
            alt_labels=alt_labels,
            broader_uri=broader_uri,
            broader_label=broader_label,
            module=module,
        )
